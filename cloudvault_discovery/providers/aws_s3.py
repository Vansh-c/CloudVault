"""
AWS S3 provider for CloudVault
Handles S3 bucket discovery with both authenticated and unauthenticated access methods,
ACL checking, owner identification, and proper rate limiting.
"""
import logging
import requests
from typing import List, Optional
from botocore.exceptions import ClientError, NoCredentialsError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
try:
    import boto3
    from boto3.session import Session
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
from ..core.worker import BaseWorker, WorkerResult, AccessLevel
from ..core.queue_manager import ProviderType
logger = logging.getLogger(__name__)
class AWSS3Worker(BaseWorker):
    """
    AWS S3 worker for bucket discovery
    Supports both authenticated (via AWS credentials) and unauthenticated methods.
    Authenticated mode provides better rate limits, ACL checking, and owner identification.
    """
    def __init__(self, config, queue_manager, result_handler, keywords=None, *args, **kwargs):
        """
        Initialize AWS S3 worker
        Args:
            config: Configuration object with AWS settings
            queue_manager: Queue manager instance
            result_handler: Function to handle found buckets
            keywords: List of keywords for interesting content detection
        """
        super().__init__("aws", config, queue_manager, result_handler, keywords, *args, **kwargs)
        self.aws_config = config.aws
        self.use_boto3 = BOTO3_AVAILABLE and self.aws_config.is_authenticated()
        if self.use_boto3:
            self._init_boto3_session()
        else:
            self._init_http_session()
        logger.info(f"AWS S3 worker initialized (authenticated: {self.use_boto3})")
    def _init_boto3_session(self):
        try:
            self.session = Session(
                aws_access_key_id=self.aws_config.access_key,
                aws_secret_access_key=self.aws_config.secret_key,
                region_name=self.aws_config.region
            )
            boto_config = BotoConfig(
                max_pool_connections=50,
                retries={'max_attempts': 3, 'mode': 'adaptive'},
                read_timeout=self.aws_config.timeout,
                connect_timeout=self.aws_config.timeout
            )
            self.s3_client = self.session.client('s3', config=boto_config)
            self.s3_resource = self.session.resource('s3', config=boto_config)
            try:
                self.s3_client.list_buckets(MaxKeys=1)
                logger.info("AWS credentials validated successfully")
            except ClientError as e:
                if e.response['Error']['Code'] in ['InvalidAccessKeyId', 'SignatureDoesNotMatch']:
                    logger.warning("Invalid AWS credentials, falling back to HTTP mode")
                    raise
                else:
                    logger.info("AWS credentials valid but limited permissions")
        except Exception as e:
            logger.warning(f"Failed to initialize boto3 session, falling back to HTTP: {e}")
            self.use_boto3 = False
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
        self.http_session.timeout = self.aws_config.timeout
    def get_provider_type(self):
        return ProviderType.AWS
    def check_target(self, target) -> WorkerResult:
        """
        Check if an S3 bucket exists and get its properties
        Args:
            target: BucketTarget to check
        Returns:
            WorkerResult: Result of the bucket check
        """
        bucket_name = target.name
        bucket_url = f"https://{bucket_name}.s3.amazonaws.com"
        if self.use_boto3:
            return self._check_bucket_boto3(bucket_name, bucket_url, target)
        else:
            return self._check_bucket_http(bucket_name, bucket_url, target)
    def _check_bucket_boto3(self, bucket_name: str, bucket_url: str, target) -> WorkerResult:
        try:
            self.s3_client.head_bucket(Bucket=bucket_name)
            result = WorkerResult(
                bucket_name=bucket_name,
                provider="aws",
                found=True,
                access_level=AccessLevel.PRIVATE,  # Default, will be updated
                bucket_url=bucket_url
            )
            try:
                location = self.s3_client.get_bucket_location(Bucket=bucket_name)
                region = location.get('LocationConstraint') or 'us-east-1'
                result.region = region
                if region == 'us-east-1':
                    result.bucket_url = f"https://{bucket_name}.s3.amazonaws.com"
                else:
                    result.bucket_url = f"https://{bucket_name}.s3.{region}.amazonaws.com"
            except ClientError:
                result.region = 'unknown'
                result.bucket_url = bucket_url
            try:
                acl = self.s3_client.get_bucket_acl(Bucket=bucket_name)
                result.owner = acl.get('Owner', {}).get('DisplayName', '(unknown)')
                result.owner_id = acl.get('Owner', {}).get('ID')
                result.access_level = self._determine_access_level_from_acl(acl)
                result.acl_info = self._format_acl_info(acl)
            except ClientError as e:
                if e.response['Error']['Code'] == 'AccessDenied':
                    result.access_level = AccessLevel.PRIVATE
                    result.acl_info = {'error': 'Access denied to ACL'}
                else:
                    logger.warning(f"Error getting ACL for {bucket_name}: {e}")
            if result.is_public or not self.config.only_interesting:
                try:
                    self._get_bucket_contents(bucket_name, result)
                except ClientError:
                    pass  # Ignore errors when listing contents
            return result
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchBucket':
                return WorkerResult(
                    bucket_name=bucket_name,
                    provider="aws", 
                    found=False,
                    access_level=AccessLevel.UNKNOWN,
                    bucket_url=bucket_url
                )
            elif error_code == 'AccessDenied':
                return WorkerResult(
                    bucket_name=bucket_name,
                    provider="aws",
                    found=True,
                    access_level=AccessLevel.PRIVATE,
                    bucket_url=bucket_url,
                    error_message="Access denied"
                )
            else:
                raise  # Re-raise other errors
    def _check_bucket_http(self, bucket_name: str, bucket_url: str, target) -> WorkerResult:
        try:
            s3_url = "http://s3-1-w.amazonaws.com"
            response = self.http_session.head(
                s3_url,
                headers={"Host": bucket_url.replace("https://", "").replace("http://", "")},
                timeout=self.aws_config.timeout
            )
            if response.status_code == 307:
                location = response.headers.get('Location', bucket_url)
                result = WorkerResult(
                    bucket_name=bucket_name,
                    provider="aws",
                    found=True,
                    access_level=AccessLevel.UNKNOWN,
                    bucket_url=location
                )
                try:
                    list_response = self.http_session.get(
                        location,
                        timeout=self.aws_config.timeout
                    )
                    if list_response.status_code == 200:
                        result.access_level = AccessLevel.PUBLIC_READ
                        content = list_response.text
                        if '<Key>' in content:
                            objects = self._extract_objects_from_xml(content)
                            result.sample_objects = objects[:10]  # First 10 objects
                            result.object_count = len(objects)
                            if self.keywords:
                                result.interesting_objects = self._check_for_interesting_content(objects)
                    elif list_response.status_code == 403:
                        result.access_level = AccessLevel.PRIVATE
                except Exception as e:
                    logger.debug(f"Error checking bucket contents for {bucket_name}: {e}")
                return result
            elif response.status_code == 404:
                return WorkerResult(
                    bucket_name=bucket_name,
                    provider="aws",
                    found=False,
                    access_level=AccessLevel.UNKNOWN,
                    bucket_url=bucket_url
                )
            elif response.status_code == 503 and response.reason == "Slow Down":
                raise Exception("AWS rate limit exceeded")
            else:
                return WorkerResult(
                    bucket_name=bucket_name,
                    provider="aws",
                    found=False,
                    access_level=AccessLevel.UNKNOWN,
                    bucket_url=bucket_url,
                    error_message=f"HTTP {response.status_code}"
                )
        except requests.exceptions.Timeout:
            logger.debug(f"Timeout checking bucket {bucket_name}")
            return WorkerResult(
                bucket_name=bucket_name,
                provider="aws",
                found=False,
                access_level=AccessLevel.UNKNOWN,
                bucket_url=bucket_url,
                error_message="Timeout"
            )
        except Exception as e:
            logger.debug(f"Error checking bucket {bucket_name}: {e}")
            raise
    def _determine_access_level_from_acl(self, acl: dict) -> AccessLevel:
        grants = acl.get('Grants', [])
        public_read = False
        public_write = False
        authenticated_read = False
        for grant in grants:
            grantee = grant.get('Grantee', {})
            permission = grant.get('Permission', '')
            if grantee.get('Type') == 'Group':
                uri = grantee.get('URI', '')
                if 'AllUsers' in uri:
                    if permission in ['READ', 'FULL_CONTROL']:
                        public_read = True
                    if permission in ['WRITE', 'FULL_CONTROL']:
                        public_write = True
                elif 'AuthenticatedUsers' in uri:
                    if permission in ['READ', 'FULL_CONTROL']:
                        authenticated_read = True
        if public_write and public_read:
            return AccessLevel.PUBLIC_READ_WRITE
        elif public_write:
            return AccessLevel.PUBLIC_WRITE
        elif public_read:
            return AccessLevel.PUBLIC_READ
        elif authenticated_read:
            return AccessLevel.AUTHENTICATED_READ
        else:
            return AccessLevel.PRIVATE
    def _format_acl_info(self, acl: dict) -> dict:
        grants = acl.get('Grants', [])
        formatted = {
            'AllUsers': [],
            'AuthenticatedUsers': [],
            'Owner': acl.get('Owner', {}).get('DisplayName', 'Unknown')
        }
        for grant in grants:
            grantee = grant.get('Grantee', {})
            permission = grant.get('Permission', '')
            if grantee.get('Type') == 'Group':
                uri = grantee.get('URI', '')
                if 'AllUsers' in uri:
                    formatted['AllUsers'].append(permission)
                elif 'AuthenticatedUsers' in uri:
                    formatted['AuthenticatedUsers'].append(permission)
        return formatted
    def _get_bucket_contents(self, bucket_name: str, result: WorkerResult):
        try:
            bucket = self.s3_resource.Bucket(bucket_name)
            objects = []
            for obj in bucket.objects.limit(100):
                objects.append(obj.key)
            result.sample_objects = objects[:10]  # First 10 for display
            result.object_count = len(objects)
            if self.keywords and objects:
                result.interesting_objects = self._check_for_interesting_content(objects)
        except ClientError as e:
            logger.debug(f"Error listing objects in {bucket_name}: {e}")
    def _extract_objects_from_xml(self, xml_content: str) -> List[str]:
        import re
        pattern = r'<Key>(.*?)</Key>'
        matches = re.findall(pattern, xml_content)
        return matches
    def is_rate_limit_error(self, error: Exception) -> bool:
        error_str = str(error).lower()
        if 'rate limit' in error_str or 'slow down' in error_str:
            return True
        if isinstance(error, ClientError):
            error_code = error.response.get('Error', {}).get('Code', '')
            if error_code in ['SlowDown', 'RequestLimitExceeded', 'Throttling']:
                return True
        if hasattr(error, 'response') and hasattr(error.response, 'status_code'):
            if error.response.status_code == 503:
                return True
        return False