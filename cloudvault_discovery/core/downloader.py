import os
import requests
import zipfile
import tarfile
import io
import hashlib
import magic
import re
import json
import sqlite3
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse
import concurrent.futures
from pathlib import Path
class BucketDownloader:
    def __init__(self, max_file_size=50*1024*1024):
        self.max_file_size = max_file_size
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    def download_file(self, url: str) -> Optional[bytes]:
        try:
            response = self.session.get(url, stream=True, timeout=30)
            if response.status_code != 200:
                return None
            content = b""
            for chunk in response.iter_content(chunk_size=8192):
                content += chunk
                if len(content) > self.max_file_size:
                    break
            return content
        except:
            return None
    def download_and_analyze_bucket(self, bucket_url: str, objects: List[str]) -> Dict[str, Any]:
        results = {
            'downloaded_files': [],
            'credentials': [],
            'databases': [],
            'configs': [],
            'sensitive_data': [],
            'metadata': {},
            'hashes': {}
        }
        priority_files = self._prioritize_files(objects)
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for obj in priority_files[:20]:
                file_url = urljoin(bucket_url.rstrip('/') + '/', obj)
                future = executor.submit(self._analyze_file, file_url, obj)
                futures.append(future)
            for future in concurrent.futures.as_completed(futures, timeout=60):
                try:
                    file_result = future.result()
                    if file_result:
                        results['downloaded_files'].append(file_result)
                        if file_result.get('credentials'):
                            results['credentials'].extend(file_result['credentials'])
                        if file_result.get('sensitive_data'):
                            results['sensitive_data'].extend(file_result['sensitive_data'])
                except:
                    pass
        return results
    def _prioritize_files(self, objects: List[str]) -> List[str]:
        priority_patterns = [
            (r'\.env$', 10), (r'config\.(json|yaml|yml)$', 9),
            (r'\.(sql|db|sqlite)$', 9), (r'\.key$|\.pem$', 8),
            (r'backup|dump', 7), (r'\.zip$|\.tar\.gz$', 6),
            (r'\.log$', 5), (r'\.txt$', 4)
        ]
        scored_files = []
        for obj in objects:
            score = 0
            for pattern, points in priority_patterns:
                if re.search(pattern, obj, re.I):
                    score = max(score, points)
            scored_files.append((obj, score))
        return [obj for obj, score in sorted(scored_files, key=lambda x: x[1], reverse=True)]
    def _analyze_file(self, url: str, filename: str) -> Optional[Dict[str, Any]]:
        content = self.download_file(url)
        if not content:
            return None
        file_hash = hashlib.md5(content).hexdigest()
        file_type = magic.from_buffer(content, mime=True) if hasattr(magic, 'from_buffer') else 'unknown'
        result = {
            'filename': filename,
            'url': url,
            'size': len(content),
            'hash': file_hash,
            'type': file_type,
            'credentials': [],
            'sensitive_data': [],
            'metadata': {}
        }
        if filename.lower().endswith(('.zip', '.tar.gz')):
            result.update(self._analyze_archive(content))
        elif filename.lower().endswith(('.sql', '.db', '.sqlite')):
            result.update(self._analyze_database(content))
        elif filename.lower().endswith(('.json', '.yaml', '.yml', '.env')):
            result.update(self._analyze_config(content))
        else:
            result.update(self._analyze_text(content))
        return result
    def _analyze_archive(self, content: bytes) -> Dict[str, Any]:
        result = {'archive_contents': [], 'extracted_files': 0}
        try:
            if zipfile.is_zipfile(io.BytesIO(content)):
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    result['archive_contents'] = zf.namelist()[:100]
                    result['extracted_files'] = len(zf.namelist())
                    for name in result['archive_contents'][:10]:
                        try:
                            file_data = zf.read(name)
                            if len(file_data) < 1024*1024:
                                creds = self._extract_credentials(file_data.decode('utf-8', errors='ignore'))
                                result['credentials'].extend(creds)
                        except:
                            pass
        except:
            pass
        return result
    def _analyze_database(self, content: bytes) -> Dict[str, Any]:
        result = {'tables': [], 'records': 0, 'db_type': 'unknown'}
        try:
            if b'SQLite format' in content[:100]:
                result['db_type'] = 'sqlite'
                temp_file = f'/tmp/temp_db_{os.getpid()}.db'
                with open(temp_file, 'wb') as f:
                    f.write(content)
                try:
                    conn = sqlite3.connect(temp_file)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                    result['tables'] = [row[0] for row in cursor.fetchall()]
                    for table in result['tables'][:5]:
                        try:
                            cursor.execute(f"SELECT * FROM {table} LIMIT 10")
                            rows = cursor.fetchall()
                            for row in rows:
                                row_str = str(row)
                                creds = self._extract_credentials(row_str)
                                result['credentials'].extend(creds)
                        except:
                            pass
                    conn.close()
                except:
                    pass
                finally:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
        except:
            pass
        return result
    def _analyze_config(self, content: bytes) -> Dict[str, Any]:
        result = {'config_keys': [], 'credentials': []}
        try:
            text = content.decode('utf-8', errors='ignore')
            if text.strip().startswith('{'):
                try:
                    data = json.loads(text)
                    result['config_keys'] = list(data.keys()) if isinstance(data, dict) else []
                    result['credentials'].extend(self._extract_credentials_from_dict(data))
                except:
                    pass
            result['credentials'].extend(self._extract_credentials(text))
        except:
            pass
        return result
    def _analyze_text(self, content: bytes) -> Dict[str, Any]:
        result = {'credentials': [], 'sensitive_data': []}
        try:
            text = content.decode('utf-8', errors='ignore')
            result['credentials'].extend(self._extract_credentials(text))
            result['sensitive_data'].extend(self._extract_sensitive_data(text))
        except:
            pass
        return result
    def _extract_credentials(self, text: str) -> List[Dict[str, str]]:
        credentials = []
        patterns = {
            'aws_access_key': r'AKIA[0-9A-Z]{16}',
            'aws_secret_key': r'[A-Za-z0-9/+=]{40}',
            'api_key': r'(?i)api[_-]?key[\'"\s]*[:=][\'"\s]*([a-z0-9_-]{20,})',
            'password': r'(?i)password[\'"\s]*[:=][\'"\s]*([^\s\'";]{6,})',
            'token': r'(?i)token[\'"\s]*[:=][\'"\s]*([a-z0-9_-]{20,})',
            'secret': r'(?i)secret[\'"\s]*[:=][\'"\s]*([a-z0-9_-]{10,})',
            'private_key': r'-----BEGIN [A-Z ]*PRIVATE KEY-----',
            'jwt_token': r'eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*',
            'github_token': r'ghp_[A-Za-z0-9]{36}',
            'slack_token': r'xox[baprs]-([0-9a-zA-Z]{10,48})',
            'discord_token': r'[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27}',
            'google_api': r'AIza[0-9A-Za-z-_]{35}',
            'facebook_token': r'EAA[A-Z0-9]+',
            'twitter_bearer': r'AAAAAAAAAAAAAAAAAAAAA[A-Za-z0-9%]+',
            'stripe_key': r'sk_live_[0-9a-zA-Z]{24}',
            'mailgun_key': r'key-[0-9a-f]{32}',
            'sendgrid_key': r'SG\.[0-9A-Za-z-_]{22}\.[0-9A-Za-z-_]{43}',
            'database_url': r'(?:mysql|postgresql|mongodb)://[^\s]+',
            'connection_string': r'(?i)(?:server|host|hostname)[\'"\s]*[:=][\'"\s]*([^\s\'";]+)',
        }
        for cred_type, pattern in patterns.items():
            matches = re.findall(pattern, text)
            for match in matches:
                credentials.append({
                    'type': cred_type,
                    'value': match if isinstance(match, str) else match[0] if match else '',
                    'context': text[max(0, text.find(str(match))-50):text.find(str(match))+100]
                })
        return credentials
    def _extract_credentials_from_dict(self, data: Any, path: str = "") -> List[Dict[str, str]]:
        credentials = []
        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key
                if any(sensitive in key.lower() for sensitive in ['key', 'secret', 'token', 'password', 'pass']):
                    credentials.append({
                        'type': 'config_credential',
                        'key': current_path,
                        'value': str(value),
                        'context': f"{key}: {value}"
                    })
                if isinstance(value, (dict, list)):
                    credentials.extend(self._extract_credentials_from_dict(value, current_path))
        elif isinstance(data, list):
            for i, item in enumerate(data):
                credentials.extend(self._extract_credentials_from_dict(item, f"{path}[{i}]"))
        return credentials
    def _extract_sensitive_data(self, text: str) -> List[Dict[str, str]]:
        sensitive_data = []
        patterns = {
            'email': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'phone': r'(?:\+?1[-.\s]?)?(?:\(?[0-9]{3}\)?[-.\s]?)?[0-9]{3}[-.\s]?[0-9]{4}',
            'ssn': r'\b\d{3}-\d{2}-\d{4}\b',
            'credit_card': r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
            'ip_address': r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
            'bitcoin_address': r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b',
            'ethereum_address': r'\b0x[a-fA-F0-9]{40}\b',
        }
        for data_type, pattern in patterns.items():
            matches = re.findall(pattern, text)
            for match in matches:
                sensitive_data.append({
                    'type': data_type,
                    'value': match,
                    'context': text[max(0, text.find(match)-30):text.find(match)+50]
                })
        return sensitive_data