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
            total=2,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=50,
            pool_block=False
        )
        self.http_session.mount("http://", adapter)
        self.http_session.mount("https://", adapter)
        self.http_session.timeout = self.gcp_config.timeout
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
                if result.is_public or not self.config.only_interesting:
                    try:
                        self._get_bucket_contents(bucket, result)
                    except Exception as e:
                        logger.debug(f"Error getting bucket contents: {e}")
            except Forbidden:
                result.access_level = AccessLevel.PRIVATE
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
                'owner': ''
            }
            for acl in bucket.acl.get():
                entity = acl.get('entity', '')
                role = acl.get('role', '')
                if entity == 'allUsers':
                    acl_info['public_access'].append(role)
                elif entity == 'allAuthenticatedUsers':
                    acl_info['authenticated_access'].append(role)
                elif 'OWNER' in role:
                    acl_info['owner'] = entity
            return acl_info
        except Exception as e:
            logger.debug(f"Error getting ACLs for {bucket.name}: {e}")
            return {'error': str(e)}
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