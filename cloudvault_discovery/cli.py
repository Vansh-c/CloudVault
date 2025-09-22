import argparse
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import List, Optional
from termcolor import cprint
import requests
from .core.config import Config
from .core.cert_stream import CertStreamMonitor, StaticDomainProcessor
from .core.queue_manager import BucketQueue, ProviderType
from .core.worker import BaseWorker, WorkerResult, UpdateThread
from .core.permutations import PermutationGenerator, load_keywords
from .core.advanced import BucketVulnerabilityScanner, BucketContentAnalyzer
from .core.downloader import BucketDownloader
from .core.exploiter import CredentialValidator
from .core.stealth import StealthSession, DistributedScanner, AntiDetection
from .core.network import NetworkObfuscator, TrafficShaping, GeoEvasion
from .core.forensics import EvidenceShredder, ProcessObfuscation, AntiAnalysis, LogManipulator, NetworkFootprintReducer
from .providers.aws_s3 import AWSS3Worker
from .providers.gcp_storage import GCPStorageWorker  
from .providers.azure_blob import AzureBlobWorker
logger = logging.getLogger(__name__)
class CloudVaultDiscovery:
    def __init__(self):
        self.config = None
        self.queue_manager = None
        self.workers = []
        self.cert_monitor = None
        self.update_thread = None
        self.permutation_generator = None
        self.keywords = []
        self.found_buckets = []
        self.vulnerability_findings = []
        self.shutdown_requested = False
        self.vuln_scanner = BucketVulnerabilityScanner()
        self.content_analyzer = BucketContentAnalyzer()
        self.downloader = None
        self.exploiter = None
        self.stealth_components = {}
    def setup_logging(self, log_level: str = "INFO", stealth_mode: bool = False):
        if stealth_mode and 'log_manipulator' in self.stealth_components:
            self.stealth_components['log_manipulator'].suppress_logging()
            return
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        logging.getLogger('urllib3').setLevel(logging.ERROR)
        logging.getLogger('requests').setLevel(logging.ERROR)
        logging.getLogger('boto3').setLevel(logging.ERROR)
        logging.getLogger('botocore').setLevel(logging.ERROR)
        logging.getLogger('websockets').setLevel(logging.WARNING)
        logging.getLogger('filelock').setLevel(logging.ERROR)
        if log_level.upper() != "DEBUG":
            logging.getLogger('cloudvault_discovery.core.queue_manager').setLevel(logging.WARNING)
    def load_config(self, config_path: str) -> bool:
        try:
            self.config = Config.from_file(config_path)
            logger.info("Configuration loaded successfully")
            return True
        except FileNotFoundError:
            cprint(f"Configuration file not found: {config_path}", "red")
            cprint("Run 'cloudvault --init-config' to create a default config", "yellow")
            return False
        except Exception as e:
            cprint(f"Error loading configuration: {e}", "red")
            return False
    def initialize_components(self, args):
        if getattr(args, 'stealth', False) or getattr(args, 'anti_forensics', False) or getattr(args, 'process_masking', False):
            self._initialize_stealth_systems(args)
        self.permutation_generator = PermutationGenerator(
            args.permutations or self.config.permutation_file
        )
        self.keywords = load_keywords(
            args.keywords_file or self.config.keywords_file
        )
        self.queue_manager = BucketQueue(
            self.config, 
            max_queue_size=self.config.queue_size
        )
        if getattr(args, 'download', False):
            self.downloader = BucketDownloader(self.config)
            logger.info("Bucket downloader initialized")
        if getattr(args, 'exploit', False):
            self.exploiter = CredentialValidator()
            logger.info("Credential validator initialized")
        self._initialize_workers(args)
        if not args.source:
            self.cert_monitor = CertStreamMonitor(
                self.queue_manager,
                self.config,
                self.permutation_generator.generate_permutations
            )
        self.update_thread = UpdateThread(
            self.queue_manager,
            self.workers,
            self.config.update_interval
        )
        logger.info("All components initialized successfully")
    def _initialize_workers(self, args):
        self.workers = []
        if self.config.aws.enabled:
            worker_count = min(
                args.threads if args.threads else self.config.aws.max_threads,
                self.config.aws.max_threads if self.config.aws.is_authenticated() else 5
            )
            for i in range(worker_count):
                worker = AWSS3Worker(
                    self.config, self.queue_manager, 
                    self.handle_found_bucket, self.keywords
                )
                self.workers.append(worker)
            logger.info(f"Initialized {worker_count} AWS S3 workers")
        if self.config.gcp.enabled:
            worker_count = min(
                args.threads if args.threads else self.config.gcp.max_threads,
                self.config.gcp.max_threads if self.config.gcp.is_authenticated() else 5
            )
            for i in range(worker_count):
                worker = GCPStorageWorker(
                    self.config, self.queue_manager,
                    self.handle_found_bucket, self.keywords
                )
                self.workers.append(worker)
            logger.info(f"Initialized {worker_count} GCP Storage workers")
        if self.config.azure.enabled:
            worker_count = min(
                args.threads if args.threads else self.config.azure.max_threads,
                self.config.azure.max_threads if self.config.azure.is_authenticated() else 5
            )
            for i in range(worker_count):
                worker = AzureBlobWorker(
                    self.config, self.queue_manager,
                    self.handle_found_bucket, self.keywords
                )
                self.workers.append(worker)
            logger.info(f"Initialized {worker_count} Azure Blob workers")
        if not self.workers:
            cprint("No workers initialized! Enable at least one provider in config.", "red")
            sys.exit(1)
    def handle_found_bucket(self, result: WorkerResult):
        self.found_buckets.append(result)
        vulnerabilities = []
        content_summary = ""
        if result.is_public and result.sample_objects:
            vulnerabilities = self.vuln_scanner.scan_bucket_contents(
                result.sample_objects, result.bucket_url
            )
            self.vulnerability_findings.extend(vulnerabilities)
            if self.downloader:
                try:
                    downloaded_files = self.downloader.download_sample_files(
                        result.bucket_url, result.sample_objects[:5]
                    )
                    if downloaded_files:
                        cprint(f"  └─ Downloaded {len(downloaded_files)} files for analysis", "blue")
                        if self.exploiter:
                            credentials = self.downloader.extract_credentials_from_files(downloaded_files)
                            if credentials:
                                cprint(f"  └─ Found {len(credentials)} potential credentials", "red", attrs=["bold"])
                                validated = self.exploiter.validate_credentials(credentials)
                                for valid_cred in validated:
                                    cprint(f"  └─ ⚠️  VALID CREDENTIAL: {valid_cred['type']} -> {valid_cred['service']}", "red", attrs=["bold", "blink"])
                except Exception as e:
                    logger.debug(f"Error during download/analysis: {e}")
            categorized = self.content_analyzer.analyze_content_types(result.sample_objects)
            content_summary = self.content_analyzer.generate_content_summary(categorized)
            sensitivity = self.content_analyzer.estimate_data_sensitivity(categorized)
        color = "green"  # Default for found buckets
        if vulnerabilities:
            if any(v.severity == "CRITICAL" for v in vulnerabilities):
                color = "red"
            elif any(v.severity == "HIGH" for v in vulnerabilities):
                color = "yellow"
        elif not result.is_public:
            color = "magenta"
        access_info = f"[{result.access_level.value.upper()}]"
        message = f"Found {result.provider.upper()} bucket: {result.bucket_url} {access_info}"
        if result.owner:
            message += f" (Owner: {result.owner})"
        if content_summary and content_summary != "No sensitive content detected":
            message += f" - Contains: {content_summary}"
        if vulnerabilities:
            critical_count = sum(1 for v in vulnerabilities if v.severity == "CRITICAL")
            high_count = sum(1 for v in vulnerabilities if v.severity == "HIGH")
            if critical_count > 0:
                message += f" ⚠️  {critical_count} CRITICAL vulnerabilities!"
            elif high_count > 0:
                message += f" ⚠️  {high_count} HIGH risk findings!"
        cprint(message, color, attrs=["bold"])
        for vuln in vulnerabilities[:3]:  # Show first 3 vulnerabilities
            cprint(f"  └─ {vuln.severity}: {vuln.title} - {vuln.evidence}", 
                   "red" if vuln.severity == "CRITICAL" else "yellow")
        if self.config.log_to_file:
            self._log_to_file(result, vulnerabilities)
        if self.config.slack_webhook:
            self._send_to_slack(message)
    def _log_to_file(self, result: WorkerResult, vulnerabilities=None):
        try:
            with open(self.config.log_file, 'a') as f:
                f.write(f"{result.bucket_url}\n")
                if vulnerabilities:
                    vuln_file = self.config.log_file.replace('.log', '_vulnerabilities.log')
                    with open(vuln_file, 'a') as vf:
                        for vuln in vulnerabilities:
                            vf.write(f"{result.bucket_url},{vuln.severity},{vuln.title},{vuln.evidence}\n")
        except Exception as e:
            logger.error(f"Error writing to log file: {e}")
    def _send_to_slack(self, message: str):
        try:
            payload = {'text': message}
            response = requests.post(
                self.config.slack_webhook,
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            if response.status_code != 200:
                logger.warning(f"Slack webhook returned {response.status_code}")
        except Exception as e:
            logger.error(f"Error sending to Slack: {e}")
    def _initialize_stealth_systems(self, args):
        if getattr(args, 'anti_forensics', False):
            self.stealth_components['evidence_shredder'] = EvidenceShredder()
            self.stealth_components['log_manipulator'] = LogManipulator()
            print("[STEALTH] Anti-forensics systems activated")
        if getattr(args, 'process_masking', False):
            self.stealth_components['process_obfuscator'] = ProcessObfuscation()
            self.stealth_components['process_obfuscator'].mask_process_name()
            self.stealth_components['decoy_processes'] = self.stealth_components['process_obfuscator'].create_decoy_processes()
            print("[STEALTH] Process masking enabled")
        if getattr(args, 'stealth', False):
            self.stealth_components['anti_analysis'] = AntiAnalysis()
            if self.stealth_components['anti_analysis'].detect_virtualization():
                print("[STEALTH] Virtualization detected - activating countermeasures")
                self.stealth_components['anti_analysis'].anti_debugging_sleep()
            self.stealth_components['stealth_session'] = StealthSession()
            self.stealth_components['network_obfuscator'] = NetworkObfuscator()
            self.stealth_components['traffic_shaping'] = TrafficShaping()
            self.stealth_components['traffic_shaping'].set_profile(getattr(args, 'traffic_shaping', 'residential'))
            self.stealth_components['geo_evasion'] = GeoEvasion()
            self.stealth_components['geo_evasion'].set_exit_country(getattr(args, 'geo_country', 'US'))
            if getattr(args, 'proxy_rotation', False):
                self.stealth_components['distributed_scanner'] = DistributedScanner()
                self.stealth_components['distributed_scanner'].setup_infrastructure()
                print("[STEALTH] Proxy rotation and distributed scanning enabled")
            self.stealth_components['network_reducer'] = NetworkFootprintReducer()
            cover_thread = self.stealth_components['network_reducer'].generate_cover_traffic()
            self.stealth_components['cover_traffic_thread'] = cover_thread
            country = getattr(args, 'geo_country', 'US')
            profile = getattr(args, 'traffic_shaping', 'residential')
            print(f"[STEALTH] Full stealth mode activated - Country: {country}, Profile: {profile}")
    def run(self, args):
        stealth_mode = bool(self.stealth_components)
        self.setup_logging(self.config.log_level, stealth_mode)
        total_threads = len(self.workers)
        total_patterns = self.permutation_generator.get_pattern_count()
        enabled_providers = ", ".join(self.config.get_enabled_providers())
        cprint(
            f"Starting CloudVault v2.0.0",
            "green", attrs=["bold"]
        )
        cprint(
            f"Providers: {enabled_providers} | Workers: {total_threads} | Patterns: {total_patterns}",
            "cyan"
        )
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        try:
            for worker in self.workers:
                worker.start()
            self.update_thread.start()
            if args.source:
                processor = StaticDomainProcessor(
                    self.queue_manager,
                    self.permutation_generator.generate_permutations
                )
                domains_processed = processor.process_file(args.source)
            else:
                self.cert_monitor.start()
            while not self.shutdown_requested:
                try:
                    time.sleep(1)
                    if args.source and self.queue_manager.is_empty():
                        if all(not worker.is_alive() for worker in self.workers):
                            cprint("All work completed!", "green")
                            break
                except KeyboardInterrupt:
                    break
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            self.shutdown()
        finally:
            self.shutdown()
    def _signal_handler(self, signum, frame):
        cprint("\nShutdown requested, cleaning up...", "yellow", attrs=["bold"])
        self.shutdown_requested = True
        self.shutdown()
    def shutdown(self):
        if self.shutdown_requested:
            return  # Already shutting down
        self.shutdown_requested = True
        try:
            if self.cert_monitor and self.cert_monitor.is_alive():
                self.cert_monitor.stop()
                self.cert_monitor.join(timeout=2)
            for worker in self.workers:
                if worker.is_alive():
                    worker.stop()
            for worker in self.workers:
                if worker.is_alive():
                    worker.join(timeout=2)
            if self.update_thread and self.update_thread.is_alive():
                self.update_thread.stop()
                self.update_thread.join(timeout=1)
            if self.queue_manager:
                self.queue_manager.shutdown()
            self._cleanup_stealth_systems()
            if self.workers and not hasattr(self, '_stats_printed'):
                self._print_final_stats()
                self._stats_printed = True
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        finally:
            logger.info("CloudVault shutdown complete")
    def _print_final_stats(self):
        total_checked = sum(w.get_stats()['checked'] for w in self.workers)
        total_found = len(self.found_buckets)
        public_found = sum(1 for r in self.found_buckets if r.is_public)
        interesting_found = sum(1 for r in self.found_buckets if r.has_interesting_content)
        critical_vulns = sum(1 for v in self.vulnerability_findings if v.severity == "CRITICAL")
        high_vulns = sum(1 for v in self.vulnerability_findings if v.severity == "HIGH")
        total_vulns = len(self.vulnerability_findings)
        cprint("\n=== Final Statistics ===", "cyan", attrs=["bold"])
        cprint(f"Buckets checked: {total_checked}", "white")
        cprint(f"Buckets found: {total_found}", "green")
        cprint(f"Public buckets: {public_found}", "yellow")
        cprint(f"Interesting buckets: {interesting_found}", "red")
        if total_vulns > 0:
            cprint(f"\n=== Security Findings ===", "red", attrs=["bold"])
            cprint(f"Total vulnerabilities: {total_vulns}", "white")
            if critical_vulns > 0:
                cprint(f"Critical vulnerabilities: {critical_vulns}", "red", attrs=["bold"])
            if high_vulns > 0:
                cprint(f"High-risk findings: {high_vulns}", "yellow")
        if self.found_buckets:
            cprint(f"\nResults logged to: {self.config.log_file}", "cyan")
            if self.vulnerability_findings:
                vuln_file = self.config.log_file.replace('.log', '_vulnerabilities.log')
                cprint(f"Vulnerabilities logged to: {vuln_file}", "cyan")
    def _cleanup_stealth_systems(self):
        if not self.stealth_components:
            return
        if 'evidence_shredder' in self.stealth_components:
            self.stealth_components['evidence_shredder'].emergency_cleanup()
            print("[STEALTH] Evidence elimination completed")
        if 'decoy_processes' in self.stealth_components and 'process_obfuscator' in self.stealth_components:
            self.stealth_components['process_obfuscator'].cleanup_decoy_processes(
                self.stealth_components['decoy_processes']
            )
            print("[STEALTH] Decoy processes terminated")
        if 'log_manipulator' in self.stealth_components:
            self.stealth_components['log_manipulator'].restore_logging()
            print("[STEALTH] Logging restored")
        if 'cover_traffic_thread' in self.stealth_components:
            print("[STEALTH] Background cover traffic terminated")
def create_default_config():
    config_path = "config.yaml"
    try:
        Config.create_default_config(config_path)
        cprint(f"Default configuration created: {config_path}", "green")
        cprint("Please edit the configuration file and add your cloud credentials.", "yellow")
    except Exception as e:
        cprint(f"Error creating default config: {e}", "red")
        return False
    return True
def main():
    parser = argparse.ArgumentParser(
        description="CloudVault - Multi-cloud storage bucket discovery via certificate transparency",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  cloudvault                              # Monitor certificate transparency logs
  cloudvault --source domains.txt        # Process static domain list
  cloudvault --only-interesting          # Only report buckets with interesting content
  cloudvault --init-config               # Create default configuration
        """
    )
    parser.add_argument("-c", "--config", default="config.yaml",
                      help="Configuration file path (default: config.yaml)")
    parser.add_argument("--init-config", action="store_true",
                      help="Create a default configuration file and exit")
    parser.add_argument("-s", "--source", 
                      help="Static domain list file instead of live certificate stream")
    parser.add_argument("-p", "--permutations", 
                      help="Permutation patterns file (overrides config)")
    parser.add_argument("--keywords-file",
                      help="Keywords file for interesting content detection (overrides config)")
    parser.add_argument("-t", "--threads", type=int,
                      help="Override number of worker threads per provider")
    parser.add_argument("--only-interesting", action="store_true",
                      help="Only report buckets with interesting content")
    parser.add_argument("--skip-lets-encrypt", action="store_true", 
                      help="Skip certificates issued by Let's Encrypt")
    parser.add_argument("-l", "--log-to-file", action="store_true",
                      help="Log found buckets to file")
    parser.add_argument("-v", "--verbose", action="store_true",
                      help="Enable verbose logging")
    parser.add_argument("--aws-only", action="store_true",
                      help="Only check AWS S3 buckets")
    parser.add_argument("--gcp-only", action="store_true", 
                      help="Only check Google Cloud Storage buckets")
    parser.add_argument("--azure-only", action="store_true",
                      help="Only check Azure Blob Storage containers")
    parser.add_argument("--download", action="store_true",
                      help="Enable real-time bucket content downloading and analysis")
    parser.add_argument("--exploit", action="store_true",
                      help="Enable credential exploitation and validation")
    parser.add_argument("--exploit-timeout", type=int, default=300,
                      help="Exploitation timeout in seconds")
    parser.add_argument("--stealth", action="store_true",
                      help="Enable advanced stealth and evasion techniques")
    parser.add_argument("--proxy-rotation", action="store_true",
                      help="Enable proxy rotation for anonymity")
    parser.add_argument("--traffic-shaping", choices=['residential', 'mobile', 'corporate', 'satellite'],
                      default='residential', help="Traffic pattern simulation")
    parser.add_argument("--geo-country", type=str, default='US',
                      help="Geographic location simulation (US, GB, DE, etc.)")
    parser.add_argument("--anti-forensics", action="store_true",
                      help="Enable evidence elimination and anti-forensics")
    parser.add_argument('--process-masking', action='store_true',
                        help='Enable process masking to hide from monitoring tools')
    
    parser.add_argument('--db-wordlist', type=str,
                        help='Wordlist file for database brute-forcing')
    
    args = parser.parse_args()
    
    if args.init_config:
        if create_default_config():
            sys.exit(0)
        else:
            sys.exit(1)
    app = CloudVaultDiscovery()
    if not app.load_config(args.config):
        sys.exit(1)
    if args.only_interesting:
        app.config.only_interesting = True
    if args.skip_lets_encrypt:
        app.config.skip_lets_encrypt = True
    if args.log_to_file:
        app.config.log_to_file = True
    if args.verbose:
        app.config.log_level = "DEBUG"
    if args.aws_only:
        app.config.gcp.enabled = False
        app.config.azure.enabled = False
    elif args.gcp_only:
        app.config.aws.enabled = False
        app.config.azure.enabled = False
    elif args.azure_only:
        app.config.aws.enabled = False
        app.config.gcp.enabled = False
    try:
        app.initialize_components(args)
        app.run(args)
    except KeyboardInterrupt:
        cprint("\nInterrupted by user", "yellow")
    except Exception as e:
        cprint(f"Fatal error: {e}", "red")
        logger.exception("Fatal error occurred")
        sys.exit(1)
if __name__ == "__main__":
    main()