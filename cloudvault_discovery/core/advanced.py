"""
Advanced features for CloudVault
Includes DNS enumeration, vulnerability scanning, and content analysis capabilities.
"""
import dns.resolver
import logging
import re
from typing import List, Dict, Set, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
logger = logging.getLogger(__name__)
@dataclass
class VulnerabilityFinding:
    severity: str  # CRITICAL, HIGH, MEDIUM, LOW
    title: str
    description: str
    bucket_url: str
    evidence: Optional[str] = None
    remediation: Optional[str] = None
class DNSBucketEnumerator:
    """
    Enumerate buckets using DNS resolution techniques
    This can help find buckets that don't follow standard naming patterns
    or discover additional buckets related to a domain.
    """
    def __init__(self):
        self.resolver = dns.resolver.Resolver()
        self.resolver.timeout = 5
        self.resolver.lifetime = 10
    def enumerate_s3_buckets(self, domain: str) -> List[str]:
        """
        Enumerate S3 buckets using DNS techniques
        Args:
            domain: Domain to enumerate buckets for
        Returns:
            List[str]: Found bucket names
        """
        buckets = []
        patterns = [
            f"{domain}.s3.amazonaws.com",
            f"s3.{domain}",
            f"{domain}-s3",
            f"s3-{domain}",
            f"{domain}.s3-website.amazonaws.com",
            f"{domain}.s3-website-us-east-1.amazonaws.com",
            f"{domain}.s3-website-us-west-1.amazonaws.com",
            f"{domain}.s3-website-us-west-2.amazonaws.com",
            f"{domain}.s3-website-eu-west-1.amazonaws.com",
        ]
        for pattern in patterns:
            try:
                answers = self.resolver.resolve(pattern, 'CNAME')
                for answer in answers:
                    bucket_name = self._extract_bucket_from_cname(str(answer))
                    if bucket_name:
                        buckets.append(bucket_name)
                        logger.info(f"Found S3 bucket via DNS: {bucket_name}")
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, Exception):
                continue
        return list(set(buckets))  # Remove duplicates
    def _extract_bucket_from_cname(self, cname: str) -> Optional[str]:
        patterns = [
            r'(\w+)\.s3\.amazonaws\.com',
            r'(\w+)\.s3-website-[\w-]+\.amazonaws\.com',
            r's3-[\w-]+\.amazonaws\.com/(\w+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, cname)
            if match:
                return match.group(1)
        return None
class BucketVulnerabilityScanner:
    """
    Scan buckets for security vulnerabilities and misconfigurations
    """
    def __init__(self):
        self.critical_patterns = [
            r'\.sql$', r'\.db$', r'\.sqlite$', r'\.dump$',
            r'\.env$', r'config\.json$', r'\.conf$', r'settings\.json$',
            r'credential', r'password', r'secret', r'token', r'key\.json$',
            r'\.bak$', r'\.backup$', r'\.old$', r'\.save$',
            r'\.git/', r'\.svn/', r'\.hg/',
            r'\.zip$', r'\.tar\.gz$', r'\.rar$', r'\.7z$'
        ]
        self.high_patterns = [
            r'\.log$', r'access_log', r'error_log',
            r'\.pdf$', r'\.doc$', r'\.docx$', r'readme', r'\.md$',
            r'\.csv$', r'\.xlsx?$', r'export', r'dump',
            r'\.pem$', r'\.key$', r'\.crt$', r'\.p12$'
        ]
    def scan_bucket_contents(self, bucket_objects: List[str], bucket_url: str) -> List[VulnerabilityFinding]:
        """
        Scan bucket contents for vulnerabilities
        Args:
            bucket_objects: List of object keys in the bucket
            bucket_url: URL of the bucket
        Returns:
            List[VulnerabilityFinding]: Found vulnerabilities
        """
        findings = []
        if not bucket_objects:
            return findings
        critical_files = self._find_matching_files(bucket_objects, self.critical_patterns)
        for file_path in critical_files:
            findings.append(VulnerabilityFinding(
                severity="CRITICAL",
                title="Sensitive File Exposure",
                description=f"Critical file exposed: {file_path}",
                bucket_url=bucket_url,
                evidence=file_path,
                remediation="Remove sensitive files or make bucket private"
            ))
        high_risk_files = self._find_matching_files(bucket_objects, self.high_patterns)
        for file_path in high_risk_files:
            findings.append(VulnerabilityFinding(
                severity="HIGH",
                title="Potentially Sensitive File",
                description=f"Potentially sensitive file exposed: {file_path}",
                bucket_url=bucket_url,
                evidence=file_path,
                remediation="Review file contents and consider making bucket private"
            ))
        if any('../' in obj or '..\\' in obj for obj in bucket_objects):
            findings.append(VulnerabilityFinding(
                severity="MEDIUM",
                title="Potential Directory Traversal",
                description="Bucket contains paths with directory traversal patterns",
                bucket_url=bucket_url,
                remediation="Review object naming and access patterns"
            ))
        if self._check_subdomain_takeover_risk(bucket_url):
            findings.append(VulnerabilityFinding(
                severity="HIGH",
                title="Subdomain Takeover Risk",
                description="Bucket name could be used for subdomain takeover attacks",
                bucket_url=bucket_url,
                remediation="Use random bucket names or ensure proper DNS configuration"
            ))
        return findings
    def _find_matching_files(self, objects: List[str], patterns: List[str]) -> List[str]:
        matching = []
        for obj in objects:
            obj_lower = obj.lower()
            for pattern in patterns:
                if re.search(pattern, obj_lower):
                    matching.append(obj)
                    break
        return matching
    def _check_subdomain_takeover_risk(self, bucket_url: str) -> bool:
        patterns = [
            r'[\w-]+\.[\w-]+\.s3',  # domain.subdomain pattern
            r'(www|api|admin|app|dev|test|staging)',  # common subdomain names
        ]
        for pattern in patterns:
            if re.search(pattern, bucket_url.lower()):
                return True
        return False
class BucketContentAnalyzer:
    """
    Analyze bucket contents for interesting data and patterns
    """
    def __init__(self):
        self.data_types = {
            'databases': ['.sql', '.db', '.sqlite', '.dump', '.bak'],
            'credentials': ['credential', 'password', 'secret', 'token', 'key', '.env'],
            'configs': ['config', 'settings', '.conf', '.ini', '.yaml', '.yml'],
            'backups': ['.bak', '.backup', '.old', '.save', '.zip', '.tar'],
            'logs': ['.log', 'access_log', 'error_log', 'debug'],
            'source_code': ['.git', '.svn', '.py', '.js', '.php', '.java'],
            'documents': ['.pdf', '.doc', '.docx', '.xls', '.xlsx'],
            'certificates': ['.pem', '.key', '.crt', '.p12', '.pfx']
        }
    def analyze_content_types(self, bucket_objects: List[str]) -> Dict[str, List[str]]:
        """
        Analyze and categorize bucket contents
        Args:
            bucket_objects: List of object keys
        Returns:
            Dict[str, List[str]]: Categorized objects
        """
        categorized = {category: [] for category in self.data_types.keys()}
        for obj in bucket_objects:
            obj_lower = obj.lower()
            for category, patterns in self.data_types.items():
                for pattern in patterns:
                    if pattern in obj_lower:
                        categorized[category].append(obj)
                        break
        return categorized
    def estimate_data_sensitivity(self, categorized_objects: Dict[str, List[str]]) -> str:
        """
        Estimate overall data sensitivity level
        Args:
            categorized_objects: Objects categorized by type
        Returns:
            str: Sensitivity level (CRITICAL, HIGH, MEDIUM, LOW)
        """
        critical_categories = ['databases', 'credentials', 'certificates']
        high_categories = ['configs', 'backups', 'source_code']
        medium_categories = ['logs', 'documents']
        for category in critical_categories:
            if categorized_objects[category]:
                return "CRITICAL"
        for category in high_categories:
            if categorized_objects[category]:
                return "HIGH"
        for category in medium_categories:
            if categorized_objects[category]:
                return "MEDIUM"
        return "LOW"
    def generate_content_summary(self, categorized_objects: Dict[str, List[str]]) -> str:
        summary_parts = []
        for category, objects in categorized_objects.items():
            if objects:
                count = len(objects)
                summary_parts.append(f"{count} {category}")
        if not summary_parts:
            return "No sensitive content detected"
        return ", ".join(summary_parts)