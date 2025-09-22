"""
Azure Blob Storage provider for CloudVault
Implements Azure Blob Storage container discovery with authentication
and public access testing for Azure containers.
"""
import logging
import requests
from typing import List, Optional
from urllib.parse import urlencode
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
try:
    from azure.storage.blob import BlobServiceClient, ContainerClient
    from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
from ..core.worker import BaseWorker, WorkerResult, AccessLevel
from ..core.queue_manager import ProviderType
logger = logging.getLogger(__name__)
class AzureBlobWorker(BaseWorker):
    def __init__(self, config, queue_manager, result_handler, keywords=None, *args, **kwargs):
        super().__init__("azure", config, queue_manager, result_handler, keywords, *args, **kwargs)
        self.azure_config = config.azure
        self.use_azure_sdk = AZURE_AVAILABLE and self.azure_config.is_authenticated()
        if self.use_azure_sdk:
            self._init_azure_client()
        else:
            self._init_http_session()
        logger.info(f"Azure Blob worker initialized (authenticated: {self.use_azure_sdk})")
    def _init_azure_client(self):
        try:
            if self.azure_config.connection_string:
                self.blob_service_client = BlobServiceClient.from_connection_string(
                    self.azure_config.connection_string
                )
            elif self.azure_config.account_name and self.azure_config.account_key:
                account_url = f"https://{self.azure_config.account_name}.blob.core.windows.net"
                self.blob_service_client = BlobServiceClient(
                    account_url=account_url,
                    credential=self.azure_config.account_key
                )
            else:
                raise Exception("No Azure credentials provided")
            next(self.blob_service_client.list_containers(max_results=1), None)
            logger.info("Azure credentials validated successfully")
        except Exception as e:
            logger.warning(f"Failed to initialize Azure client, falling back to HTTP: {e}")
            self.use_azure_sdk = False
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
        self.http_session.timeout = self.azure_config.timeout
    def get_provider_type(self):
        return ProviderType.AZURE
    def check_target(self, target) -> WorkerResult:
        container_name = target.name
        storage_accounts = self._generate_storage_account_names(container_name)
        for account_name in storage_accounts:
            container_url = f"https://{account_name}.blob.core.windows.net/{container_name}"
            if self.use_azure_sdk:
                result = self._check_container_azure(container_name, container_url, account_name, target)
            else:
                result = self._check_container_http(container_name, container_url, account_name, target)
            if result.found:
                return result
        return WorkerResult(
            bucket_name=container_name,
            provider="azure", 
            found=False,
            access_level=AccessLevel.UNKNOWN,
            bucket_url=f"https://[account].blob.core.windows.net/{container_name}"
        )
    def _generate_storage_account_names(self, container_name: str) -> List[str]:
        base_names = [container_name]
        patterns = [
            container_name,
            f"{container_name}storage",
            f"{container_name}data",
            f"{container_name}blob",
            f"storage{container_name}",
            f"data{container_name}",
            f"blob{container_name}",
            container_name.replace("-", ""),
            container_name.replace("_", ""),
        ]
        valid_accounts = []
        for pattern in patterns:
            clean_name = ''.join(c for c in pattern.lower() if c.isalnum())
            if 3 <= len(clean_name) <= 24:
                valid_accounts.append(clean_name)
        return list(dict.fromkeys(valid_accounts))[:5]  # Limit to first 5 to avoid too many requests
    def _check_container_azure(self, container_name: str, container_url: str, account_name: str, target) -> WorkerResult:
        try:
            container_client = self.blob_service_client.get_container_client(container_name)
            properties = container_client.get_container_properties()
            result = WorkerResult(
                bucket_name=container_name,
                provider="azure",
                found=True,
                access_level=AccessLevel.PRIVATE,
                bucket_url=container_url
            )
            public_access = properties.get('public_access', 'none')
            if public_access == 'container':
                result.access_level = AccessLevel.PUBLIC_READ
            elif public_access == 'blob':
                result.access_level = AccessLevel.PUBLIC_READ
            else:
                result.access_level = AccessLevel.PRIVATE
            result.acl_info = {
                'public_access': public_access,
                'account_name': account_name
            }
            if result.is_public or not self.config.only_interesting:
                try:
                    self._get_container_contents(container_client, result)
                except Exception as e:
                    logger.debug(f"Error getting container contents: {e}")
            return result
        except ResourceNotFoundError:
            return WorkerResult(
                bucket_name=container_name,
                provider="azure",
                found=False,
                access_level=AccessLevel.UNKNOWN,
                bucket_url=container_url
            )
        except HttpResponseError as e:
            if e.status_code == 403:
                return WorkerResult(
                    bucket_name=container_name,
                    provider="azure",
                    found=True,
                    access_level=AccessLevel.PRIVATE,
                    bucket_url=container_url,
                    error_message="Access denied"
                )
            elif e.status_code == 429:
                raise  # Re-raise rate limit errors
            else:
                return WorkerResult(
                    bucket_name=container_name,
                    provider="azure",
                    found=False,
                    access_level=AccessLevel.UNKNOWN,
                    bucket_url=container_url,
                    error_message=str(e)
                )
        except Exception as e:
            logger.debug(f"Error checking Azure container {container_name}: {e}")
            return WorkerResult(
                bucket_name=container_name,
                provider="azure",
                found=False,
                access_level=AccessLevel.UNKNOWN,
                bucket_url=container_url,
                error_message=str(e)
            )
    def _check_container_http(self, container_name: str, container_url: str, account_name: str, target) -> WorkerResult:
        try:
            response = self.http_session.head(
                container_url,
                timeout=self.azure_config.timeout
            )
            if response.status_code == 200:
                result = WorkerResult(
                    bucket_name=container_name,
                    provider="azure",
                    found=True,
                    access_level=AccessLevel.PUBLIC_READ,
                    bucket_url=container_url
                )
                try:
                    list_url = f"{container_url}?restype=container&comp=list"
                    list_response = self.http_session.get(
                        list_url,
                        timeout=self.azure_config.timeout
                    )
                    if list_response.status_code == 200:
                        content = list_response.text
                        objects = self._extract_objects_from_xml(content)
                        result.sample_objects = objects[:10]
                        result.object_count = len(objects)
                        if self.keywords:
                            result.interesting_objects = self._check_for_interesting_content(objects)
                except Exception as e:
                    logger.debug(f"Error listing blobs in Azure container {container_name}: {e}")
                return result
            elif response.status_code == 403:
                return WorkerResult(
                    bucket_name=container_name,
                    provider="azure",
                    found=True,
                    access_level=AccessLevel.PRIVATE,
                    bucket_url=container_url
                )
            elif response.status_code == 404:
                return WorkerResult(
                    bucket_name=container_name,
                    provider="azure",
                    found=False,
                    access_level=AccessLevel.UNKNOWN,
                    bucket_url=container_url
                )
            elif response.status_code == 429:
                raise Exception("Azure rate limit exceeded")
            else:
                return WorkerResult(
                    bucket_name=container_name,
                    provider="azure",
                    found=False,
                    access_level=AccessLevel.UNKNOWN,
                    bucket_url=container_url,
                    error_message=f"HTTP {response.status_code}"
                )
        except requests.exceptions.Timeout:
            return WorkerResult(
                bucket_name=container_name,
                provider="azure",
                found=False,
                access_level=AccessLevel.UNKNOWN,
                bucket_url=container_url,
                error_message="Timeout"
            )
        except Exception as e:
            if "rate limit" in str(e).lower() or "429" in str(e):
                raise  # Re-raise rate limit errors
            logger.debug(f"Error checking Azure container {container_name}: {e}")
            return WorkerResult(
                bucket_name=container_name,
                provider="azure",
                found=False,
                access_level=AccessLevel.UNKNOWN,
                bucket_url=container_url,
                error_message=str(e)
            )
    def _get_container_contents(self, container_client, result: WorkerResult):
        try:
            objects = []
            blobs = container_client.list_blobs(max_results=100)
            for blob in blobs:
                objects.append(blob.name)
            result.sample_objects = objects[:10]
            result.object_count = len(objects)
            if self.keywords and objects:
                result.interesting_objects = self._check_for_interesting_content(objects)
        except Exception as e:
            logger.debug(f"Error listing blobs in container: {e}")
    def _extract_objects_from_xml(self, xml_content: str) -> List[str]:
        import re
        pattern = r'<Name>(.*?)</Name>'
        matches = re.findall(pattern, xml_content)
        return matches
    def is_rate_limit_error(self, error: Exception) -> bool:
        error_str = str(error).lower()
        if '429' in error_str or 'rate limit' in error_str or 'throttl' in error_str:
            return True
        if AZURE_AVAILABLE:
            if isinstance(error, HttpResponseError) and error.status_code == 429:
                return True
        if hasattr(error, 'response') and hasattr(error.response, 'status_code'):
            if error.response.status_code == 429:
                return True
        return False