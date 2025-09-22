"""
Certificate Transparency monitoring system for CloudVault
Modern implementation of certificate transparency log monitoring with improved
error handling, reconnection logic, and domain extraction capabilities.
"""
import asyncio
import json
import logging
import time
from threading import Thread, Event
from typing import Set, Callable, Optional, List
import tldextract
import websockets
from termcolor import cprint
logger = logging.getLogger(__name__)
class CertStreamMonitor(Thread):
    """
    Modern certificate transparency log monitor
    Connects to certificate transparency logs, extracts domains from certificates,
    and generates bucket name permutations for cloud storage discovery.
    """
    def __init__(self, 
                 queue_manager,
                 config,
                 permutation_generator: Callable[[str, str], List[str]],
                 *args, **kwargs):
        """
        Initialize certificate stream monitor
        Args:
            queue_manager: Queue manager instance to add discovered buckets
            config: Configuration object containing cert stream settings
            permutation_generator: Function to generate bucket name permutations
        """
        super().__init__(*args, **kwargs)
        self.queue_manager = queue_manager
        self.config = config
        self.permutation_generator = permutation_generator
        self.stop_event = Event()
        self.connection_attempts = 0
        self.max_connection_attempts = 10
        self.reconnect_delay = 5  # seconds
        self.excluded_patterns = {
            'cloudflaressl', 'xn--', 'letsencrypt', 'localhost',
            'internal', 'local', 'test-', '.test', '.localhost'
        }
        self.max_hyphens = 4
        self.max_dots = 4
        self.last_message_time = time.time()
        self.message_count = 0
        self.health_check_interval = 60  # seconds
    def run(self):
        while not self.stop_event.is_set() and self.connection_attempts < self.max_connection_attempts:
            try:
                cprint(
                    f"Connecting to certificate transparency stream (attempt {self.connection_attempts + 1})...",
                    "yellow", attrs=["bold"]
                )
                asyncio.run(self._connect_and_monitor())
            except Exception as e:
                self.connection_attempts += 1
                logger.error(f"Certificate stream connection failed: {e}")
                if self.connection_attempts < self.max_connection_attempts:
                    cprint(
                        f"Connection failed, retrying in {self.reconnect_delay} seconds...",
                        "yellow"
                    )
                    if self.stop_event.wait(self.reconnect_delay):
                        break
                else:
                    cprint(
                        f"Max connection attempts ({self.max_connection_attempts}) exceeded. "
                        "Certificate stream monitoring disabled.",
                        "red", attrs=["bold"]
                    )
                    break
    async def _connect_and_monitor(self):
        try:
            async with websockets.connect(
                self.config.cert_stream_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            ) as websocket:
                self.connection_attempts = 0  # Reset on successful connection
                cprint("Connected to certificate transparency stream!", "green", attrs=["bold"])
                async for message in websocket:
                    if self.stop_event.is_set():
                        break
                    try:
                        await self._process_message(json.loads(message))
                    except json.JSONDecodeError:
                        logger.warning("Received invalid JSON message from cert stream")
                    except Exception as e:
                        logger.error(f"Error processing cert stream message: {e}")
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Certificate stream connection closed")
            raise
        except Exception as e:
            logger.error(f"Certificate stream connection error: {e}")
            raise
    async def _process_message(self, message: dict):
        try:
            self.last_message_time = time.time()
            self.message_count += 1
            if message.get("message_type") == "heartbeat":
                if self.message_count % 100 == 0:  # Log every 100th heartbeat
                    logger.debug(f"Certificate stream healthy - {self.message_count} messages processed")
                return
            if message.get("message_type") == "certificate_update":
                await self._process_certificate_update(message)
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    async def _process_certificate_update(self, message: dict):
        try:
            data = message.get("data", {})
            leaf_cert = data.get("leaf_cert", {})
            all_domains = leaf_cert.get("all_domains", [])
            if self.config.skip_lets_encrypt:
                chain = data.get("chain", [])
                if chain and "Let's Encrypt" in str(chain[0].get("subject", {}).get("aggregated", "")):
                    return
            domains_processed = 0
            for domain in set(all_domains):  # Remove duplicates
                if await self._should_process_domain(domain):
                    await self._process_domain(domain)
                    domains_processed += 1
            if domains_processed > 0:
                logger.debug(f"Processed {domains_processed} domains from certificate")
        except Exception as e:
            logger.error(f"Error processing certificate update: {e}")
    async def _should_process_domain(self, domain: str) -> bool:
        """
        Determine if a domain should be processed for bucket discovery
        Args:
            domain: Domain name to evaluate
        Returns:
            bool: True if domain should be processed
        """
        if domain.startswith("*."):
            return False
        domain_lower = domain.lower()
        for pattern in self.excluded_patterns:
            if pattern in domain_lower:
                return False
        if (domain.count("-") > self.max_hyphens or 
            domain.count(".") > self.max_dots):
            return False
        if len(domain) < 3 or len(domain) > 250:
            return False
        return True
    async def _process_domain(self, domain: str):
        """
        Process a domain by generating bucket permutations
        Args:
            domain: Domain to process for bucket discovery
        """
        try:
            parts = tldextract.extract(domain)
            if not parts.domain:
                return
            permutations = self.permutation_generator(parts.domain, parts.subdomain)
            for permutation in permutations:
                if permutation:  # Skip empty permutations
                    self.queue_manager.add_target(permutation, domain)
        except Exception as e:
            logger.error(f"Error processing domain {domain}: {e}")
    def stop(self):
        logger.info("Stopping certificate stream monitor...")
        self.stop_event.set()
class StaticDomainProcessor:
    """
    Processor for static domain lists (alternative to live cert stream)
    Processes domains from a file instead of live certificate transparency logs.
    """
    def __init__(self, 
                 queue_manager,
                 permutation_generator: Callable[[str, str], List[str]]):
        """
        Initialize static domain processor
        Args:
            queue_manager: Queue manager instance to add discovered buckets  
            permutation_generator: Function to generate bucket name permutations
        """
        self.queue_manager = queue_manager
        self.permutation_generator = permutation_generator
    def process_file(self, file_path: str) -> int:
        """
        Process domains from a file
        Args:
            file_path: Path to file containing domain list
        Returns:
            int: Number of domains processed
        """
        domains_processed = 0
        try:
            with open(file_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    domain = line.strip()
                    if not domain or domain.startswith('#'):
                        continue
                    try:
                        self._process_domain(domain)
                        domains_processed += 1
                    except Exception as e:
                        logger.error(f"Error processing domain '{domain}' at line {line_num}: {e}")
            if domains_processed > 0:
                cprint(f"Processed {domains_processed} domains from {file_path}", "green")
        except FileNotFoundError:
            cprint(f"Domain file not found: {file_path}", "red")
            return 0
        except Exception as e:
            logger.error(f"Error reading domain file {file_path}: {e}")
            return 0
        return domains_processed
    def _process_domain(self, domain: str):
        """
        Process a single domain by generating bucket permutations
        Args:
            domain: Domain to process for bucket discovery
        """
        parts = tldextract.extract(domain)
        if not parts.domain:
            logger.warning(f"Could not extract domain from: {domain}")
            return
        permutations = self.permutation_generator(parts.domain, parts.subdomain)
        for permutation in permutations:
            if permutation:
                self.queue_manager.add_target(permutation, domain)