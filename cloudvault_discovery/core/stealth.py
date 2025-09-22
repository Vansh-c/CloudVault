import random
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import threading
from typing import List, Dict, Any, Optional
import itertools
import socket
import socks
from fake_useragent import UserAgent
class StealthSession:
    def __init__(self):
        self.proxies = []
        self.user_agents = []
        self.current_proxy_index = 0
        self.ua = UserAgent()
        self.sessions = {}
        self.request_delays = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        self.last_request_time = 0
    def setup_proxies(self, proxy_list: List[str]):
        self.proxies = proxy_list
        random.shuffle(self.proxies)
    def setup_user_agents(self, ua_list: List[str] = None):
        if ua_list:
            self.user_agents = ua_list
        else:
            self.user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.101 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
                'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0',
                'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36'
            ]
    def get_stealth_session(self, provider: str = 'default') -> requests.Session:
        if provider not in self.sessions:
            session = requests.Session()
            session.headers.update({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            })
            retry_strategy = Retry(
                total=3,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
                backoff_factor=random.uniform(1, 3)
            )
            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=5,
                pool_maxsize=10,
                pool_block=False
            )
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            self.sessions[provider] = session
        self._randomize_session_properties(self.sessions[provider])
        return self.sessions[provider]
    def _randomize_session_properties(self, session: requests.Session):
        if self.user_agents:
            session.headers['User-Agent'] = random.choice(self.user_agents)
        else:
            try:
                session.headers['User-Agent'] = self.ua.random
            except:
                session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        if self.proxies:
            proxy = random.choice(self.proxies)
            session.proxies = {
                'http': proxy,
                'https': proxy
            }
        optional_headers = {
            'Cache-Control': random.choice(['max-age=0', 'no-cache', 'no-store']),
            'Pragma': random.choice(['no-cache', '']),
            'Sec-Fetch-Dest': random.choice(['document', 'empty', 'script']),
            'Sec-Fetch-Mode': random.choice(['navigate', 'cors', 'no-cors']),
            'Sec-Fetch-Site': random.choice(['none', 'same-origin', 'cross-site'])
        }
        for header, value in optional_headers.items():
            if random.choice([True, False]) and value:
                session.headers[header] = value
    def stealth_request(self, method: str, url: str, session: requests.Session = None, **kwargs) -> requests.Response:
        if not session:
            session = self.get_stealth_session()
        self._apply_timing_delay()
        kwargs.setdefault('timeout', random.uniform(8, 15))
        if 'headers' not in kwargs:
            kwargs['headers'] = {}
        kwargs['headers'].setdefault('Referer', self._generate_fake_referer(url))
        try:
            response = session.request(method, url, **kwargs)
            self._handle_response(response, session)
            return response
        except requests.RequestException as e:
            if '429' in str(e) or 'rate limit' in str(e).lower():
                self._handle_rate_limit(session)
                time.sleep(random.uniform(5, 15))
                return session.request(method, url, **kwargs)
            raise
    def _apply_timing_delay(self):
        current_time = time.time()
        if self.last_request_time > 0:
            elapsed = current_time - self.last_request_time
            min_delay = random.choice(self.request_delays)
            if elapsed < min_delay:
                time.sleep(min_delay - elapsed + random.uniform(0, 0.5))
        self.last_request_time = time.time()
    def _generate_fake_referer(self, url: str) -> str:
        domain = url.split('/')[2] if len(url.split('/')) > 2 else 'google.com'
        fake_referers = [
            f'https://{domain}/',
            'https://www.google.com/',
            'https://www.bing.com/',
            'https://duckduckgo.com/',
            'https://github.com/',
            'https://stackoverflow.com/'
        ]
        return random.choice(fake_referers)
    def _handle_response(self, response: requests.Response, session: requests.Session):
        if response.status_code == 429:
            self._handle_rate_limit(session)
        elif response.status_code in [403, 406]:
            self._randomize_session_properties(session)
    def _handle_rate_limit(self, session: requests.Session):
        self._randomize_session_properties(session)
        time.sleep(random.uniform(10, 30))
class DistributedScanner:
    def __init__(self, thread_count: int = 5):
        self.stealth_session = StealthSession()
        self.thread_count = thread_count
        self.results = []
        self.result_lock = threading.Lock()
    def setup_infrastructure(self, proxies: List[str] = None, user_agents: List[str] = None):
        if not proxies:
            proxies = self._get_free_proxies()
        self.stealth_session.setup_proxies(proxies)
        self.stealth_session.setup_user_agents(user_agents)
    def _get_free_proxies(self) -> List[str]:
        proxy_sources = [
            'https://www.proxy-list.download/api/v1/get?type=http',
            'https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt',
            'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt'
        ]
        proxies = []
        for source in proxy_sources:
            try:
                response = requests.get(source, timeout=10)
                if response.status_code == 200:
                    proxy_list = response.text.strip().split('\n')
                    for proxy in proxy_list[:20]:
                        if ':' in proxy and len(proxy.split(':')) == 2:
                            ip, port = proxy.strip().split(':')
                            if self._test_proxy(ip, int(port)):
                                proxies.append(f'http://{proxy.strip()}')
                if len(proxies) >= 10:
                    break
            except:
                continue
        return proxies[:10] if proxies else []
    def _test_proxy(self, ip: str, port: int) -> bool:
        try:
            proxy = {'http': f'http://{ip}:{port}', 'https': f'http://{ip}:{port}'}
            response = requests.get('http://httpbin.org/ip', proxies=proxy, timeout=5)
            return response.status_code == 200
        except:
            return False
    def distributed_bucket_scan(self, targets: List[str], provider: str = 'aws') -> List[Dict]:
        chunks = [targets[i:i+self.thread_count] for i in range(0, len(targets), self.thread_count)]
        for chunk in chunks:
            threads = []
            for target in chunk:
                thread = threading.Thread(
                    target=self._scan_single_bucket,
                    args=(target, provider)
                )
                threads.append(thread)
                thread.start()
            for thread in threads:
                thread.join()
            time.sleep(random.uniform(2, 5))
        return self.results
    def _scan_single_bucket(self, bucket_name: str, provider: str):
        session = self.stealth_session.get_stealth_session(f'{provider}_{threading.current_thread().name}')
        if provider == 'aws':
            urls = [
                f'https://{bucket_name}.s3.amazonaws.com',
                f'https://s3.amazonaws.com/{bucket_name}',
                f'https://{bucket_name}.s3-website-us-east-1.amazonaws.com'
            ]
        elif provider == 'gcp':
            urls = [
                f'https://storage.googleapis.com/{bucket_name}',
                f'https://storage.cloud.google.com/{bucket_name}'
            ]
        elif provider == 'azure':
            account_names = ['storage', 'data', 'backup', 'files']
            urls = [f'https://{acc}{bucket_name}.blob.core.windows.net/{bucket_name}' 
                   for acc in account_names]
        for url in urls:
            try:
                response = self.stealth_session.stealth_request('HEAD', url, session)
                if response.status_code in [200, 403]:
                    result = {
                        'bucket_name': bucket_name,
                        'url': url,
                        'status_code': response.status_code,
                        'provider': provider,
                        'accessible': response.status_code == 200,
                        'headers': dict(response.headers)
                    }
                    with self.result_lock:
                        self.results.append(result)
                    break
            except Exception as e:
                continue
            time.sleep(random.uniform(0.1, 0.5))
class AntiDetection:
    @staticmethod
    def randomize_timing():
        delays = [0.1, 0.2, 0.5, 1.0, 1.5, 2.0, 3.0]
        return random.choice(delays) + random.uniform(0, 0.5)
    @staticmethod
    def generate_realistic_headers(url: str) -> Dict[str, str]:
        base_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'max-age=0',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Connection': 'keep-alive'
        }
        domain = url.split('/')[2] if len(url.split('/')) > 2 else ''
        if 'amazonaws.com' in domain:
            base_headers['X-Amz-User-Agent'] = 'aws-sdk-js/2.814.0 linux/v14.15.4 browser'
        elif 'googleapis.com' in domain:
            base_headers['X-Goog-Api-Client'] = 'gl-js/1.12.1 grpc-web/1.0.0'
        elif 'blob.core.windows.net' in domain:
            base_headers['X-MS-Client-Request-ID'] = str(random.randint(100000, 999999))
        return base_headers
    @staticmethod
    def obfuscate_requests(url: str, method: str = 'GET') -> Dict[str, Any]:
        obfuscated_params = {}
        if '?' in url:
            base_url, query_string = url.split('?', 1)
            params = dict(param.split('=') for param in query_string.split('&') if '=' in param)
            dummy_params = {
                'timestamp': str(int(time.time())),
                'rand': str(random.randint(1000, 9999)),
                'cache': str(random.randint(10000, 99999))
            }
            params.update(dummy_params)
            obfuscated_params = {'params': params}
            url = base_url
        return {
            'url': url,
            'headers': AntiDetection.generate_realistic_headers(url),
            'timeout': random.uniform(8, 15),
            **obfuscated_params
        }
    @staticmethod
    def create_decoy_requests(target_url: str) -> List[str]:
        domain = target_url.split('/')[2] if len(target_url.split('/')) > 2 else ''
        decoy_urls = [
            f'https://{domain}/',
            f'https://{domain}/favicon.ico',
            f'https://{domain}/robots.txt',
            f'https://{domain}/sitemap.xml'
        ]
        return decoy_urls
    @staticmethod
    def fingerprint_evasion() -> Dict[str, str]:
        browsers = ['chrome', 'firefox', 'safari', 'edge']
        os_systems = ['windows', 'macos', 'linux']
        browser = random.choice(browsers)
        os_sys = random.choice(os_systems)
        user_agents = {
            'chrome_windows': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'firefox_linux': 'Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'safari_macos': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15'
        }
        key = f'{browser}_{os_sys}'
        if key not in user_agents:
            key = random.choice(list(user_agents.keys()))
        return {
            'User-Agent': user_agents[key],
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': random.choice(['en-US,en;q=0.9', 'en-GB,en;q=0.9', 'en-CA,en;q=0.9']),
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': random.choice(['1', '0']),
            'Connection': 'keep-alive'
        }