"""
Configuration management for CloudVault
Handles YAML configuration files, environment variables, and provider-specific settings.
Provides validation and default values for all configuration options.
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
@dataclass
class ProviderConfig:
    enabled: bool = True
    max_threads: int = 5
    rate_limit_sleep: float = 1.0
    timeout: int = 10
@dataclass
class AWSConfig(ProviderConfig):
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    region: str = "us-east-1"
    max_threads: int = 20  # Higher limit for authenticated AWS
    def is_authenticated(self) -> bool:
        return bool(self.access_key and self.secret_key)
@dataclass
class GCPConfig(ProviderConfig):
    service_account_path: Optional[str] = None
    project_id: Optional[str] = None
    max_threads: int = 15
    def is_authenticated(self) -> bool:
        return bool(self.service_account_path and os.path.exists(self.service_account_path))
@dataclass 
class AzureConfig(ProviderConfig):
    account_name: Optional[str] = None
    account_key: Optional[str] = None
    connection_string: Optional[str] = None
    max_threads: int = 15
    def is_authenticated(self) -> bool:
        return bool((self.account_name and self.account_key) or self.connection_string)
@dataclass
class Config:
    queue_size: int = 100
    update_interval: int = 30
    log_level: str = "INFO"
    aws: AWSConfig = field(default_factory=AWSConfig)
    gcp: GCPConfig = field(default_factory=GCPConfig)
    azure: AzureConfig = field(default_factory=AzureConfig)
    cert_stream_url: str = "wss://certstream.calidog.io"
    skip_lets_encrypt: bool = False
    log_to_file: bool = False
    log_file: str = "buckets.log"
    slack_webhook: Optional[str] = None
    only_interesting: bool = False
    keywords_file: str = "keywords.txt"
    permutation_file: str = "permutations/default.txt"
    @classmethod
    def from_file(cls, config_path: str) -> 'Config':
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Config':
        config = cls()
        for key in ['queue_size', 'update_interval', 'log_level', 'cert_stream_url', 
                   'skip_lets_encrypt', 'log_to_file', 'log_file', 'slack_webhook',
                   'only_interesting', 'keywords_file', 'permutation_file']:
            if key in data:
                setattr(config, key, data[key])
        if 'aws' in data:
            aws_data = data['aws']
            config.aws = AWSConfig(
                enabled=aws_data.get('enabled', True),
                access_key=aws_data.get('access_key') or os.getenv('AWS_ACCESS_KEY_ID'),
                secret_key=aws_data.get('secret_key') or os.getenv('AWS_SECRET_ACCESS_KEY'),
                region=aws_data.get('region', 'us-east-1'),
                max_threads=aws_data.get('max_threads', 20),
                rate_limit_sleep=aws_data.get('rate_limit_sleep', 1.0),
                timeout=aws_data.get('timeout', 10)
            )
        if 'gcp' in data:
            gcp_data = data['gcp']
            config.gcp = GCPConfig(
                enabled=gcp_data.get('enabled', True),
                service_account_path=gcp_data.get('service_account_path') or os.getenv('GOOGLE_APPLICATION_CREDENTIALS'),
                project_id=gcp_data.get('project_id') or os.getenv('GOOGLE_CLOUD_PROJECT'),
                max_threads=gcp_data.get('max_threads', 15),
                rate_limit_sleep=gcp_data.get('rate_limit_sleep', 1.0),
                timeout=gcp_data.get('timeout', 10)
            )
        if 'azure' in data:
            azure_data = data['azure']
            config.azure = AzureConfig(
                enabled=azure_data.get('enabled', True),
                account_name=azure_data.get('account_name') or os.getenv('AZURE_STORAGE_ACCOUNT'),
                account_key=azure_data.get('account_key') or os.getenv('AZURE_STORAGE_KEY'),
                connection_string=azure_data.get('connection_string') or os.getenv('AZURE_STORAGE_CONNECTION_STRING'),
                max_threads=azure_data.get('max_threads', 15),
                rate_limit_sleep=azure_data.get('rate_limit_sleep', 1.0),
                timeout=azure_data.get('timeout', 10)
            )
        return config
    def to_dict(self) -> Dict[str, Any]:
        return {
            'queue_size': self.queue_size,
            'update_interval': self.update_interval,
            'log_level': self.log_level,
            'cert_stream_url': self.cert_stream_url,
            'skip_lets_encrypt': self.skip_lets_encrypt,
            'log_to_file': self.log_to_file,
            'log_file': self.log_file,
            'slack_webhook': self.slack_webhook,
            'only_interesting': self.only_interesting,
            'keywords_file': self.keywords_file,
            'permutation_file': self.permutation_file,
            'aws': {
                'enabled': self.aws.enabled,
                'access_key': self.aws.access_key,
                'secret_key': self.aws.secret_key,
                'region': self.aws.region,
                'max_threads': self.aws.max_threads,
                'rate_limit_sleep': self.aws.rate_limit_sleep,
                'timeout': self.aws.timeout
            },
            'gcp': {
                'enabled': self.gcp.enabled,
                'service_account_path': self.gcp.service_account_path,
                'project_id': self.gcp.project_id,
                'max_threads': self.gcp.max_threads,
                'rate_limit_sleep': self.gcp.rate_limit_sleep,
                'timeout': self.gcp.timeout
            },
            'azure': {
                'enabled': self.azure.enabled,
                'account_name': self.azure.account_name,
                'account_key': self.azure.account_key,
                'connection_string': self.azure.connection_string,
                'max_threads': self.azure.max_threads,
                'rate_limit_sleep': self.azure.rate_limit_sleep,
                'timeout': self.azure.timeout
            }
        }
    def save(self, config_path: str) -> None:
        with open(config_path, 'w') as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, indent=2)
    def get_enabled_providers(self) -> List[str]:
        enabled = []
        if self.aws.enabled:
            enabled.append('aws')
        if self.gcp.enabled:
            enabled.append('gcp')
        if self.azure.enabled:
            enabled.append('azure')
        return enabled
    def get_total_threads(self) -> int:
        total = 0
        if self.aws.enabled:
            threads = self.aws.max_threads if self.aws.is_authenticated() else 5
            total += threads
        if self.gcp.enabled:
            threads = self.gcp.max_threads if self.gcp.is_authenticated() else 5
            total += threads
        if self.azure.enabled:
            threads = self.azure.max_threads if self.azure.is_authenticated() else 5
            total += threads
        return total
    @staticmethod
    def create_default_config(config_path: str) -> None:
        config = Config()
        config_dir = os.path.dirname(config_path)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)
        config.save(config_path)
        print(f"Default configuration created at: {config_path}")
