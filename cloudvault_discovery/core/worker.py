"""
Base worker classes and result handling for CloudVault
Provides abstract base classes for bucket workers, result structures,
and common functionality shared across all cloud providers.
"""
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from threading import Thread, Event
from typing import List, Optional, Dict, Any, Callable
from termcolor import cprint
logger = logging.getLogger(__name__)
class AccessLevel(Enum):
    PRIVATE = "private"
    PUBLIC_READ = "public_read"
    PUBLIC_WRITE = "public_write"
    PUBLIC_READ_WRITE = "public_read_write"
    AUTHENTICATED_READ = "authenticated_read"
    UNKNOWN = "unknown"
@dataclass
class WorkerResult:
    bucket_name: str
    provider: str
    found: bool
    access_level: AccessLevel
    bucket_url: str
    region: Optional[str] = None
    endpoint_url: Optional[str] = None
    owner: Optional[str] = None
    owner_id: Optional[str] = None
    acl_info: Optional[Dict[str, Any]] = None
    object_count: Optional[int] = None
    total_size: Optional[int] = None
    sample_objects: List[str] = None
    interesting_objects: List[str] = None
    source_domain: Optional[str] = None
    check_duration: Optional[float] = None
    error_message: Optional[str] = None
    def __post_init__(self):
        if self.sample_objects is None:
            self.sample_objects = []
        if self.interesting_objects is None:
            self.interesting_objects = []
    @property
    def is_public(self) -> bool:
        return self.access_level in [
            AccessLevel.PUBLIC_READ,
            AccessLevel.PUBLIC_WRITE,
            AccessLevel.PUBLIC_READ_WRITE
        ]
    @property
    def has_interesting_content(self) -> bool:
        return len(self.interesting_objects) > 0
    def to_dict(self) -> Dict[str, Any]:
        return {
            'bucket_name': self.bucket_name,
            'provider': self.provider,
            'found': self.found,
            'access_level': self.access_level.value,
            'bucket_url': self.bucket_url,
            'region': self.region,
            'endpoint_url': self.endpoint_url,
            'owner': self.owner,
            'owner_id': self.owner_id,
            'acl_info': self.acl_info,
            'object_count': self.object_count,
            'total_size': self.total_size,
            'sample_objects': self.sample_objects,
            'interesting_objects': self.interesting_objects,
            'source_domain': self.source_domain,
            'check_duration': self.check_duration,
            'error_message': self.error_message
        }
class BaseWorker(Thread, ABC):
    """
    Abstract base class for cloud provider workers
    Handles the common threading logic, result reporting, and error handling
    that all provider workers need.
    """
    def __init__(self, 
                 provider_name: str,
                 config,
                 queue_manager,
                 result_handler: Callable[[WorkerResult], None],
                 keywords: List[str] = None,
                 *args, **kwargs):
        """
        Initialize base worker
        Args:
            provider_name: Name of the cloud provider (aws, gcp, azure)
            config: Configuration object
            queue_manager: Queue manager instance
            result_handler: Function to handle discovered buckets
            keywords: List of keywords for "interesting" content detection
        """
        super().__init__(*args, **kwargs)
        self.provider_name = provider_name
        self.config = config
        self.queue_manager = queue_manager
        self.result_handler = result_handler
        self.keywords = keywords or []
        self.stop_event = Event()
        self.daemon = True
        self.stats = {
            'checked': 0,
            'found': 0,
            'public': 0,
            'interesting': 0,
            'errors': 0
        }
        logger.info(f"Initialized {provider_name} worker")
    def run(self):
        logger.info(f"{self.provider_name} worker started")
        try:
            while not self.stop_event.is_set():
                target = self.queue_manager.get_target(
                    self.get_provider_type(), 
                    timeout=1.0  # 1 second timeout to allow periodic shutdown checks
                )
                if target is None:
                    continue  # No target available, continue loop
                try:
                    start_time = time.time()
                    result = self.check_target(target)
                    result.check_duration = time.time() - start_time
                    result.source_domain = target.source_domain
                    self._update_stats(result)
                    self.queue_manager.mark_target_completed(target, success=True)
                    if result.found:
                        self.result_handler(result)
                except Exception as e:
                    logger.error(f"Error checking {target.name}: {e}")
                    self.stats['errors'] += 1
                    if self.is_rate_limit_error(e):
                        self.queue_manager.mark_rate_limited(self.get_provider_type())
                    self.queue_manager.mark_target_completed(target, success=False)
        except Exception as e:
            logger.error(f"{self.provider_name} worker crashed: {e}")
        finally:
            logger.info(f"{self.provider_name} worker stopped")
    @abstractmethod
    def get_provider_type(self):
        pass
    @abstractmethod
    def check_target(self, target) -> WorkerResult:
        """
        Check a specific target bucket/container
        Args:
            target: BucketTarget to check
        Returns:
            WorkerResult: Result of the check
        """
        pass
    @abstractmethod
    def is_rate_limit_error(self, error: Exception) -> bool:
        """
        Check if an error indicates rate limiting
        Args:
            error: Exception that occurred
        Returns:
            bool: True if this is a rate limit error
        """
        pass
    def _update_stats(self, result: WorkerResult):
        self.stats['checked'] += 1
        if result.found:
            self.stats['found'] += 1
            if result.is_public:
                self.stats['public'] += 1
            if result.has_interesting_content:
                self.stats['interesting'] += 1
    def _check_for_interesting_content(self, objects: List[str]) -> List[str]:
        """
        Check object list for interesting content based on keywords
        Args:
            objects: List of object keys/names
        Returns:
            List[str]: Objects that match interesting keywords
        """
        if not self.keywords:
            return []
        interesting = []
        objects_text = ' '.join(objects).lower()
        for obj in objects:
            obj_lower = obj.lower()
            if any(keyword.lower() in obj_lower for keyword in self.keywords):
                interesting.append(obj)
        return interesting
    def get_stats(self) -> Dict[str, int]:
        return self.stats.copy()
    def stop(self):
        logger.info(f"Stopping {self.provider_name} worker...")
        self.stop_event.set()
class UpdateThread(Thread):
    """
    Thread that provides periodic status updates
    Shows statistics about bucket checking progress across all workers.
    """
    def __init__(self, queue_manager, workers: List[BaseWorker], update_interval: int = 30):
        """
        Initialize update thread
        Args:
            queue_manager: Queue manager to get statistics from
            workers: List of worker threads to monitor
            update_interval: How often to print updates (seconds)
        """
        super().__init__(daemon=True)
        self.queue_manager = queue_manager
        self.workers = workers
        self.update_interval = update_interval
        self.stop_event = Event()
        self.last_stats = {}
    def run(self):
        logger.info("Update thread started")
        while not self.stop_event.wait(self.update_interval):
            try:
                self._print_update()
            except Exception as e:
                logger.error(f"Error in update thread: {e}")
        logger.info("Update thread stopped")
    def _print_update(self):
        queue_stats = self.queue_manager.get_stats()
        worker_stats = {}
        total_checked = 0
        total_found = 0
        total_public = 0
        total_interesting = 0
        for worker in self.workers:
            stats = worker.get_stats()
            worker_stats[worker.provider_name] = stats
            total_checked += stats['checked']
            total_found += stats['found']
            total_public += stats['public']
            total_interesting += stats['interesting']
        current_checked = queue_stats.get('total_checked', 0)
        last_checked = self.last_stats.get('total_checked', 0)
        rate = (current_checked - last_checked) / self.update_interval if current_checked > last_checked else 0
        cprint(
            f"Status: {total_checked} checked ({rate:.1f}/s), {total_found} found, "
            f"{total_public} public, {total_interesting} interesting",
            "cyan", attrs=["bold"]
        )
        if len(worker_stats) > 1:
            for provider, stats in worker_stats.items():
                if stats['checked'] > 0:
                    cprint(
                        f"  {provider}: {stats['checked']} checked, {stats['found']} found, "
                        f"{stats['public']} public",
                        "cyan"
                    )
        self.last_stats = queue_stats.copy()
    def stop(self):
        logger.info("Stopping update thread...")
        self.stop_event.set()