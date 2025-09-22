"""
Thread-safe queue management system for CloudVault
Manages bucket discovery queues with provider-specific rate limiting,
thread-safe operations, and queue persistence capabilities.
"""
import queue
import threading
import time
import logging
from collections import defaultdict, namedtuple
from typing import Dict, Set, Optional, Tuple, List
from dataclasses import dataclass
from enum import Enum
logger = logging.getLogger(__name__)
class ProviderType(Enum):
    AWS = "aws"
    GCP = "gcp" 
    AZURE = "azure"
@dataclass
class BucketTarget:
    name: str                    # Bucket/container name
    provider: ProviderType      # Cloud provider
    source_domain: str          # Original domain that generated this target
    created_at: float           # Timestamp when target was created
    attempts: int = 0           # Number of check attempts
    last_attempt: float = 0.0   # Timestamp of last attempt
class RateLimiter:
    def __init__(self, provider: ProviderType, max_requests_per_second: float = 1.0):
        self.provider = provider
        self.max_requests_per_second = max_requests_per_second
        self.min_interval = 1.0 / max_requests_per_second if max_requests_per_second > 0 else 0
        self.last_request_time = 0.0
        self.rate_limited_until = 0.0
        self.rate_limit_count = 0
        self.lock = threading.Lock()
    def should_wait(self) -> Tuple[bool, float]:
        """
        Check if we should wait before making a request
        Returns:
            Tuple[bool, float]: (should_wait, wait_seconds)
        """
        with self.lock:
            current_time = time.time()
            if current_time < self.rate_limited_until:
                wait_time = self.rate_limited_until - current_time
                return True, wait_time
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.min_interval:
                wait_time = self.min_interval - time_since_last
                return True, wait_time
            return False, 0.0
    def record_request(self):
        with self.lock:
            self.last_request_time = time.time()
    def record_rate_limit(self, backoff_seconds: float = None):
        """
        Record that we hit a rate limit
        Args:
            backoff_seconds: How long to back off, or None for auto-calculation
        """
        with self.lock:
            self.rate_limit_count += 1
            if backoff_seconds is None:
                base_delay = 2.0
                backoff_seconds = min(base_delay * (1.5 ** self.rate_limit_count), 300)
            self.rate_limited_until = time.time() + backoff_seconds
            if backoff_seconds > 5:
                logger.warning(f"{self.provider.value} rate limited, backing off for {backoff_seconds:.1f} seconds")
            else:
                logger.debug(f"{self.provider.value} rate limited, backing off for {backoff_seconds:.1f} seconds")
    def reset_rate_limit(self):
        with self.lock:
            if self.rate_limit_count > 0:
                self.rate_limit_count = max(0, self.rate_limit_count - 1)
                logger.info(f"{self.provider.value} rate limit status improved")
class BucketQueue:
    """
    Thread-safe queue manager for bucket discovery
    Manages separate queues for each cloud provider with rate limiting,
    duplicate detection, and statistics tracking.
    """
    def __init__(self, config, max_queue_size: int = 1000):
        """
        Initialize bucket queue manager
        Args:
            config: Configuration object with provider settings
            max_queue_size: Maximum size for each provider queue
        """
        self.config = config
        self.max_queue_size = max_queue_size
        self.queues: Dict[ProviderType, queue.Queue] = {}
        self.rate_limiters: Dict[ProviderType, RateLimiter] = {}
        self.checked_targets: Set[str] = set()  # Track checked bucket names
        self.failed_targets: Set[str] = set()   # Track permanently failed targets
        self.stats = defaultdict(int)
        self.lock = threading.RLock()
        self.shutdown_event = threading.Event()
        self._initialize_providers()
    def _initialize_providers(self):
        enabled_providers = self.config.get_enabled_providers()
        for provider_name in enabled_providers:
            provider = ProviderType(provider_name)
            self.queues[provider] = queue.Queue(maxsize=self.max_queue_size)
            if provider == ProviderType.AWS:
                rate = 1.0 / self.config.aws.rate_limit_sleep if self.config.aws.rate_limit_sleep > 0 else 10.0
            elif provider == ProviderType.GCP:
                rate = 1.0 / self.config.gcp.rate_limit_sleep if self.config.gcp.rate_limit_sleep > 0 else 5.0
            elif provider == ProviderType.AZURE:
                rate = 1.0 / self.config.azure.rate_limit_sleep if self.config.azure.rate_limit_sleep > 0 else 5.0
            else:
                rate = 1.0  # Default rate
            self.rate_limiters[provider] = RateLimiter(provider, rate)
            logger.info(f"Initialized {provider.value} queue with rate limit: {rate} req/sec")
    def add_target(self, bucket_name: str, source_domain: str):
        """
        Add bucket targets for all enabled providers
        Args:
            bucket_name: Base bucket name to check
            source_domain: Domain that generated this bucket name
        """
        with self.lock:
            if not bucket_name or len(bucket_name) < 3:
                return
            for provider in self.queues.keys():
                provider_bucket_name = self._format_bucket_name(bucket_name, provider)
                if not provider_bucket_name or len(provider_bucket_name) < 3:
                    continue
                target_key = f"{provider.value}:{provider_bucket_name}"
                if target_key in self.checked_targets or target_key in self.failed_targets:
                    self.stats[f"{provider.value}_duplicate"] += 1
                    continue
                target = BucketTarget(
                    name=provider_bucket_name,
                    provider=provider,
                    source_domain=source_domain,
                    created_at=time.time()
                )
                try:
                    self.queues[provider].put_nowait(target)
                    self.stats[f"{provider.value}_queued"] += 1
                    self.checked_targets.add(target_key)
                except queue.Full:
                    self.stats[f"{provider.value}_queue_full"] += 1
                    if self.stats[f"{provider.value}_queue_full"] % 100 == 1:  # Log every 100th
                        logger.warning(f"{provider.value} queue is full, dropping targets")
    def _format_bucket_name(self, bucket_name: str, provider: ProviderType) -> str:
        """
        Format bucket name according to provider requirements
        Args:
            bucket_name: Base bucket name
            provider: Target cloud provider
        Returns:
            str: Provider-formatted bucket name
        """
        if provider == ProviderType.AWS:
            return bucket_name.lower().replace('_', '-')
        elif provider == ProviderType.GCP:
            return bucket_name.lower()
        elif provider == ProviderType.AZURE:
            formatted = bucket_name.lower().replace('_', '').strip('-')
            return formatted if formatted else bucket_name.lower()
        return bucket_name.lower()
    def get_target(self, provider: ProviderType, timeout: float = None) -> Optional[BucketTarget]:
        """
        Get next target from provider queue with rate limiting
        Args:
            provider: Cloud provider to get target for
            timeout: Maximum time to wait for a target
        Returns:
            BucketTarget or None if no target available
        """
        if provider not in self.queues:
            return None
        should_wait, wait_time = self.rate_limiters[provider].should_wait()
        if should_wait:
            if wait_time > 0:
                logger.debug(f"Rate limiting {provider.value}, waiting {wait_time:.2f}s")
                if self.shutdown_event.wait(min(wait_time, timeout or wait_time)):
                    return None  # Shutdown requested
        try:
            target = self.queues[provider].get(timeout=timeout)
            self.rate_limiters[provider].record_request()
            self.stats[f"{provider.value}_dequeued"] += 1
            return target
        except queue.Empty:
            return None
    def mark_target_completed(self, target: BucketTarget, success: bool = True):
        """
        Mark a target as completed
        Args:
            target: The completed target
            success: Whether the check was successful
        """
        with self.lock:
            target.last_attempt = time.time()
            target.attempts += 1
            if success:
                self.stats[f"{target.provider.value}_completed"] += 1
                self.rate_limiters[target.provider].reset_rate_limit()
            else:
                self.stats[f"{target.provider.value}_failed"] += 1
                if target.attempts >= 3:
                    target_key = f"{target.provider.value}:{target.name}"
                    self.failed_targets.add(target_key)
                    self.stats[f"{target.provider.value}_permanent_fail"] += 1
    def mark_rate_limited(self, provider: ProviderType, backoff_seconds: float = None):
        """
        Mark a provider as rate limited
        Args:
            provider: Cloud provider that was rate limited
            backoff_seconds: How long to back off
        """
        if provider in self.rate_limiters:
            self.rate_limiters[provider].record_rate_limit(backoff_seconds)
            self.stats[f"{provider.value}_rate_limited"] += 1
    def get_queue_sizes(self) -> Dict[str, int]:
        with self.lock:
            return {
                provider.value: q.qsize() 
                for provider, q in self.queues.items()
            }
    def get_total_queued(self) -> int:
        return sum(self.get_queue_sizes().values())
    def get_stats(self) -> Dict[str, int]:
        with self.lock:
            stats = dict(self.stats)
            stats.update(self.get_queue_sizes())
            stats['total_checked'] = len(self.checked_targets)
            stats['total_failed'] = len(self.failed_targets)
            return stats
    def is_empty(self) -> bool:
        return all(q.empty() for q in self.queues.values())
    def shutdown(self):
        logger.info("Shutting down queue manager...")
        self.shutdown_event.set()
        with self.lock:
            for provider_queue in self.queues.values():
                while not provider_queue.empty():
                    try:
                        provider_queue.get_nowait()
                    except queue.Empty:
                        break