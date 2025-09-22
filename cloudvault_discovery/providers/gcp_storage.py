"""
Google Cloud Storage provider for CloudVault
Implements GCP bucket discovery with authentication via service accounts
and public access testing for GCS buckets.
"""
import logging
import requests
import json
from typing import List, Optional, Dict
from urllib.parse import urlencode
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
try:
    from google.cloud import storage
    from google.cloud.exceptions import NotFound, Forbidden, TooManyRequests
    from google.api_core.exceptions import GoogleAPIError
    GCP_AVAILABLE = True
except ImportError:
    GCP_AVAILABLE = False
from ..core.worker import BaseWorker, WorkerResult, AccessLevel
from ..core.queue_manager import ProviderType
logger = logging.getLogger(__name__)
class GCPStorageWorker(BaseWorker):
    def __init__(self, config, queue_manager, result_handler, keywords=None, *args, **kwargs):
        super().__init__("gcp", config, queue_manager, result_handler, keywords, *args, **kwargs)
        self.gcp_config = config.gcp
        self.use_gcp_sdk = GCP_AVAILABLE and self.gcp_config.is_authenticated()
        if self.use_gcp_sdk:
            self._init_gcp_client()
        else:
            self._init_http_session()
        logger.info(f"GCP Storage worker initialized (authenticated: {self.use_gcp_sdk})")
    def _init_gcp_client(self):
        try:
            if self.gcp_config.service_account_path:
                self.storage_client = storage.Client.from_service_account_json(
                    self.gcp_config.service_account_path
                )
            else:
                self.storage_client = storage.Client(project=self.gcp_config.project_id)
            next(self.storage_client.list_buckets(max_results=1), None)
            logger.info("GCP credentials validated successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize GCP client, falling back to HTTP: {e}")
            self.use_gcp_sdk = False
            self._init_http_session()
    def _init_http_session(self):
        self.http_session = requests.Session()
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            backoff_factor=2,
            raise_on_status=False
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=15,
            pool_maxsize=100,
            pool_block=False
        )
        self.http_session.mount("http://", adapter)
        self.http_session.mount("https://", adapter)
        
        self.connect_timeout = min(self.gcp_config.timeout // 3, 10)
        self.read_timeout = self.gcp_config.timeout - self.connect_timeout
    def get_provider_type(self):
        return ProviderType.GCP
    def check_target(self, target) -> WorkerResult:
        bucket_name = target.name
        bucket_url = f"https://storage.googleapis.com/{bucket_name}"
        if self.use_gcp_sdk:
            return self._check_bucket_gcp(bucket_name, bucket_url, target)
        else:
            return self._check_bucket_http(bucket_name, bucket_url, target)
    def _check_bucket_gcp(self, bucket_name: str, bucket_url: str, target) -> WorkerResult:
        try:
            bucket = self.storage_client.bucket(bucket_name)
            exists = bucket.exists()
            if not exists:
                return WorkerResult(
                    bucket_name=bucket_name, provider="gcp", found=False,
                    access_level=AccessLevel.UNKNOWN, bucket_url=bucket_url
                )
            result = WorkerResult(
                bucket_name=bucket_name, provider="gcp", found=True, 
                access_level=AccessLevel.PRIVATE, bucket_url=bucket_url
            )
            try:
                bucket_metadata = bucket.get_iam_policy()
                result.access_level = self._determine_access_level_from_iam(bucket_metadata)
                result.region = bucket.location
                result.acl_info = self._get_bucket_acl_info(bucket)
                
                if result.acl_info and 'owner' in result.acl_info:
                    owner = result.acl_info['owner']
                    owner_type = result.acl_info.get('owner_type', '')
                    
                    if owner and owner != '(unknown)' and owner != '(error)':
                        if owner_type == 'user':
                            result.owner = f"User: {owner}"
                        elif owner_type == 'project':
                            result.owner = owner
                        else:
                            result.owner = owner
                    else:
                        result.owner = '(unknown)'
                else:
                    result.owner = '(unknown)'
                
                result.permission_analysis = self._enhance_gcp_permission_analysis(result.acl_info, bucket_name)
                
                if not self._validate_gcp_bucket_access(bucket_name, bucket_url, result.access_level):
                    logger.debug(f"Bucket {bucket_name} validation failed - marking as false positive")
                    result.found = False
                    result.error_message = "Validation failed - possible false positive"
                    return result
                
                if result.is_public or not self.config.only_interesting:
                    try:
                        self._get_bucket_contents(bucket, result)
                    except Exception as e:
                        logger.debug(f"Error getting bucket contents: {e}")
            except Forbidden:
                result.access_level = AccessLevel.PRIVATE
                result.owner = '(access denied)'
                result.error_message = "Access denied to IAM policy"
            return result
        except Forbidden:
            return WorkerResult(
                bucket_name=bucket_name, provider="gcp", found=True,
                access_level=AccessLevel.PRIVATE, bucket_url=bucket_url,
                error_message="Access denied"
            )
        except Exception as e:
            if isinstance(e, NotFound):
                return WorkerResult(
                    bucket_name=bucket_name, provider="gcp", found=False,
                    access_level=AccessLevel.UNKNOWN, bucket_url=bucket_url
                )
            elif isinstance(e, TooManyRequests):
                raise  # Re-raise rate limit errors
            else:
                logger.error(f"Error checking GCP bucket {bucket_name}: {e}")
                return WorkerResult(
                    bucket_name=bucket_name, provider="gcp", found=False,
                    access_level=AccessLevel.UNKNOWN, bucket_url=bucket_url,
                    error_message=str(e)
                )
    def _check_bucket_http(self, bucket_name: str, bucket_url: str, target) -> WorkerResult:
        try:
            response = self.http_session.head(
                bucket_url,
                timeout=self.gcp_config.timeout
            )
            if response.status_code != 404:
                access_level = AccessLevel.PRIVATE
                if response.status_code == 200:
                    access_level = AccessLevel.PUBLIC_READ
                result = WorkerResult(
                    bucket_name=bucket_name, provider="gcp", found=True,
                    access_level=access_level, bucket_url=bucket_url
                )
                if access_level == AccessLevel.PUBLIC_READ:
                    try:
                        list_url = f"{bucket_url}?list"
                        list_response = self.http_session.get(
                            list_url, 
                            timeout=self.gcp_config.timeout
                        )
                        if list_response.status_code == 200:
                            content = list_response.text
                            try:
                                json_content = json.loads(content)
                                objects = self._extract_objects_from_json(json_content)
                                result.sample_objects = objects[:10]
                                result.object_count = len(objects)
                                if self.keywords:
                                    result.interesting_objects = self._check_for_interesting_content(objects)
                            except json.JSONDecodeError:
                                objects = self._extract_objects_from_xml(content)
                                result.sample_objects = objects[:10]
                                result.object_count = len(objects)
                                if self.keywords:
                                    result.interesting_objects = self._check_for_interesting_content(objects)
                    except Exception as e:
                        logger.debug(f"Error listing objects in GCP bucket {bucket_name}: {e}")
                return result
            else:
                return WorkerResult(
                    bucket_name=bucket_name, provider="gcp", found=False,
                    access_level=AccessLevel.UNKNOWN, bucket_url=bucket_url
                )
        except requests.exceptions.Timeout:
            return WorkerResult(
                bucket_name=bucket_name, provider="gcp", found=False,
                access_level=AccessLevel.UNKNOWN, bucket_url=bucket_url,
                error_message="Timeout"
            )
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                raise  # Re-raise rate limit errors
            logger.debug(f"Error checking GCP bucket {bucket_name}: {e}")
            return WorkerResult(
                bucket_name=bucket_name, provider="gcp", found=False,
                access_level=AccessLevel.UNKNOWN, bucket_url=bucket_url,
                error_message=str(e)
            )
    def _determine_access_level_from_iam(self, policy) -> AccessLevel:
        access_level = AccessLevel.PRIVATE
        if not policy:
            return access_level
        for binding in policy.bindings:
            role = binding.role
            members = binding.members
            if 'allUsers' in members:
                if 'storage.objects.get' in role:
                    access_level = AccessLevel.PUBLIC_READ
                if 'storage.objects.create' in role:
                    if access_level == AccessLevel.PUBLIC_READ:
                        access_level = AccessLevel.PUBLIC_READ_WRITE
                    else:
                        access_level = AccessLevel.PUBLIC_WRITE
            if 'allAuthenticatedUsers' in members and access_level == AccessLevel.PRIVATE:
                access_level = AccessLevel.AUTHENTICATED_READ
        return access_level
    def _get_bucket_acl_info(self, bucket) -> dict:
        try:
            acl_info = {
                'public_access': [], 
                'authenticated_access': [],
                'owner': '',
                'owner_type': '',
                'grants': []
            }
            
            try:
                bucket_metadata = bucket.reload()
                owner_info = getattr(bucket, 'owner', None)
                if owner_info:
                    acl_info['owner'] = owner_info
                    acl_info['owner_type'] = 'project'
                elif hasattr(bucket, 'project_number'):
                    acl_info['owner'] = f"Project-{bucket.project_number}"
                    acl_info['owner_type'] = 'project'
                else:
                    acl_info['owner'] = '(unknown)'
            except Exception as e:
                logger.debug(f"Error getting bucket owner info: {e}")
                acl_info['owner'] = '(unknown)'
            
            for acl in bucket.acl.get():
                entity = acl.get('entity', '')
                role = acl.get('role', '')
                
                grant_info = {
                    'entity': entity,
                    'role': role,
                    'entity_type': self._determine_entity_type(entity)
                }
                acl_info['grants'].append(grant_info)
                
                if entity == 'allUsers':
                    acl_info['public_access'].append(role)
                elif entity == 'allAuthenticatedUsers':
                    acl_info['authenticated_access'].append(role)
                elif 'OWNER' in role and not acl_info['owner']:
                    if entity.startswith('user-'):
                        acl_info['owner'] = entity.replace('user-', '')
                        acl_info['owner_type'] = 'user'
                    elif entity.startswith('project-'):
                        acl_info['owner'] = entity
                        acl_info['owner_type'] = 'project'
                    else:
                        acl_info['owner'] = entity
                        acl_info['owner_type'] = 'unknown'
                        
            return acl_info
        except Exception as e:
            logger.debug(f"Error getting ACLs for {bucket.name}: {e}")
            return {'error': str(e), 'owner': '(error)'}

    def _determine_entity_type(self, entity: str) -> str:
        if entity == 'allUsers':
            return 'public'
        elif entity == 'allAuthenticatedUsers':
            return 'authenticated'
        elif entity.startswith('user-'):
            return 'user'
        elif entity.startswith('group-'):
            return 'group'
        elif entity.startswith('domain-'):
            return 'domain'
        elif entity.startswith('project-'):
            return 'project'
        else:
            return 'unknown'

    def _enhance_gcp_permission_analysis(self, acl_info: dict, bucket_name: str) -> dict:
        analysis = {
            'public_read': False,
            'public_write': False,
            'authenticated_read': False,
            'bucket_policy_only': acl_info.get('bucket_policy_only', False),
            'risk_level': 'LOW'
        }
        
        grants = acl_info.get('grants', [])
        for grant in grants:
            grantee = grant.get('entity', '').lower()
            permission = grant.get('role', '').upper()
            
            if 'allusers' in grantee:
                if 'READER' in permission:
                    analysis['public_read'] = True
                    analysis['risk_level'] = 'HIGH'
                elif 'WRITER' in permission or 'OWNER' in permission:
                    analysis['public_write'] = True
                    analysis['risk_level'] = 'CRITICAL'
            elif 'allauthenticatedusers' in grantee:
                analysis['authenticated_read'] = True
                analysis['risk_level'] = 'MEDIUM'
        
        if analysis['bucket_policy_only']:
            if analysis['risk_level'] == 'HIGH':
                analysis['risk_level'] = 'MEDIUM'
            elif analysis['risk_level'] == 'CRITICAL':
                analysis['risk_level'] = 'HIGH'
        
        return analysis

    def _validate_gcp_bucket_access(self, bucket_name: str, bucket_url: str, access_level) -> bool:
        try:
            if hasattr(access_level, 'name') and 'PUBLIC' in access_level.name:
                response = self.http_session.head(bucket_url, timeout=self.gcp_config.timeout)
                if response.status_code in [200, 403]:
                    return True
                elif response.status_code == 404:
                    logger.debug(f"Public bucket validation failed for {bucket_name}: 404 Not Found")
                    return False
            
            if self.use_gcp_client:
                try:
                    bucket = self.storage_client.bucket(bucket_name)
                    bucket.reload()
                    return True
                except NotFound:
                    logger.debug(f"Bucket validation failed for {bucket_name}: NotFound")
                    return False
                except Forbidden:
                    return self._verify_gcp_bucket_via_http(bucket_url)
            else:
                return self._verify_gcp_bucket_via_http(bucket_url)
                    
        except Exception as e:
            logger.debug(f"GCP validation error for {bucket_name}: {e}")
            return True
            
        return True

    def _verify_gcp_bucket_via_http(self, bucket_url: str) -> bool:
        try:
            response = self.http_session.head(bucket_url, timeout=self.gcp_config.timeout)
            if response.status_code in [200, 403]:
                return True
            elif response.status_code == 404:
                return False
            return True
            
        except Exception as e:
            logger.debug(f"GCP HTTP verification failed: {e}")
            return True
    def _get_bucket_contents(self, bucket, result: WorkerResult):
        try:
            objects = []
            blobs = self.storage_client.list_blobs(bucket, max_results=100)
            for blob in blobs:
                objects.append(blob.name)
            result.sample_objects = objects[:10]
            result.object_count = len(objects)
            if self.keywords and objects:
                result.interesting_objects = self._check_for_interesting_content(objects)
        except Exception as e:
            logger.debug(f"Error listing objects in GCP bucket {bucket.name}: {e}")
    def _extract_objects_from_json(self, json_content: dict) -> List[str]:
        objects = []
        items = json_content.get('items', [])
        if not items and 'prefixes' in json_content:
            items = json_content.get('prefixes', [])
        for item in items:
            if isinstance(item, str):
                objects.append(item)
            elif isinstance(item, dict) and 'name' in item:
                objects.append(item['name'])
        return objects
    def _extract_objects_from_xml(self, xml_content: str) -> List[str]:
        import re
        pattern = r'<Key>(.*?)</Key>'
        matches = re.findall(pattern, xml_content)
        if not matches:
            pattern = r'<Name>(.*?)</Name>'
            matches = re.findall(pattern, xml_content)
        return matches
    def is_rate_limit_error(self, error: Exception) -> bool:
        error_str = str(error).lower()
        if '429' in error_str or 'rate limit' in error_str or 'quota' in error_str:
            return True
        if GCP_AVAILABLE:
            if isinstance(error, TooManyRequests):
                return True
            if isinstance(error, GoogleAPIError) and '429' in str(error):
                return True
        if hasattr(error, 'response') and hasattr(error.response, 'status_code'):
            if error.response.status_code == 429:
                return True
        return False