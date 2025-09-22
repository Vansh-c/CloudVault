"""
Bucket name permutation system for CloudVault
Generates bucket name variations that work across all cloud providers,
with configurable permutation files and domain-based generation.
"""
import logging
import os
from typing import List, Set, Optional
from pathlib import Path
logger = logging.getLogger(__name__)
class PermutationGenerator:
    """
    Generates bucket name permutations from domain names
    Supports loading permutation patterns from files and generating
    provider-specific bucket name variations.
    """
    def __init__(self, permutation_file_path: str = None):
        """
        Initialize permutation generator
        Args:
            permutation_file_path: Path to file containing permutation patterns
        """
        self.permutation_patterns = []
        self.base_patterns = [
            "{domain}",
            "www-{domain}",
            "{domain}-www",
        ]
        if permutation_file_path and os.path.exists(permutation_file_path):
            self.load_permutation_file(permutation_file_path)
        else:
            logger.warning(f"Permutation file not found: {permutation_file_path}, using default patterns")
            self.permutation_patterns = self.base_patterns.copy()
    def load_permutation_file(self, file_path: str) -> int:
        """
        Load permutation patterns from file
        Args:
            file_path: Path to permutation file
        Returns:
            int: Number of patterns loaded
        """
        patterns = []
        try:
            with open(file_path, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '{' in line and '}' in line:
                        pattern = line.replace('%s', '{domain}')
                        patterns.append(pattern)
                    else:
                        logger.warning(f"Invalid pattern at line {line_num} in {file_path}: {line}")
            if patterns:
                self.permutation_patterns = self.base_patterns + patterns
                logger.info(f"Loaded {len(patterns)} permutation patterns from {file_path}")
            else:
                logger.warning(f"No valid patterns found in {file_path}, using defaults")
                self.permutation_patterns = self.base_patterns.copy()
        except Exception as e:
            logger.error(f"Error loading permutation file {file_path}: {e}")
            self.permutation_patterns = self.base_patterns.copy()
        return len(self.permutation_patterns) - len(self.base_patterns)
    def generate_permutations(self, domain: str, subdomain: str = None) -> List[str]:
        """
        Generate bucket name permutations for a domain
        Args:
            domain: Main domain (e.g., 'example')
            subdomain: Optional subdomain (e.g., 'api')
        Returns:
            List[str]: Generated bucket name permutations
        """
        if not domain:
            return []
        permutations = set()
        for pattern in self.permutation_patterns:
            try:
                bucket_name = pattern.format(domain=domain)
                if self._is_valid_bucket_name(bucket_name):
                    permutations.add(bucket_name)
            except (KeyError, ValueError) as e:
                logger.debug(f"Error with pattern '{pattern}': {e}")
                continue
        if subdomain and subdomain != 'www':
            subdomain_patterns = [
                f"{subdomain}-{domain}",
                f"{domain}-{subdomain}",
                f"{subdomain}.{domain}".replace('.', '-'),
                f"{subdomain}_{domain}".replace('_', '-'),  # Convert for S3 compatibility
            ]
            for pattern in subdomain_patterns:
                if self._is_valid_bucket_name(pattern):
                    permutations.add(pattern)
        valid_permutations = []
        for perm in permutations:
            if self._is_valid_bucket_name(perm):
                valid_permutations.append(perm)
        return sorted(valid_permutations)
    def _is_valid_bucket_name(self, name: str) -> bool:
        """
        Validate bucket name against general cloud storage naming rules
        Args:
            name: Bucket name to validate
        Returns:
            bool: True if name is valid
        """
        if not name:
            return False
        if len(name) < 3 or len(name) > 63:
            return False
        if not name.replace('-', '').isalnum():
            return False
        if name.startswith(('-', '.', '_')) or name.endswith(('-', '.', '_')):
            return False
        if '--' in name or '..' in name or '__' in name:
            return False
        if name.isdigit():
            return False
        return True
    def get_pattern_count(self) -> int:
        return len(self.permutation_patterns)
    def add_custom_patterns(self, patterns: List[str]):
        """
        Add custom permutation patterns
        Args:
            patterns: List of pattern strings with {domain} placeholder
        """
        for pattern in patterns:
            if '{domain}' in pattern:
                self.permutation_patterns.append(pattern)
                logger.debug(f"Added custom pattern: {pattern}")
            else:
                logger.warning(f"Invalid custom pattern (missing {{domain}}): {pattern}")
def load_keywords(keywords_file: str) -> List[str]:
    """
    Load keywords for interesting content detection
    Args:
        keywords_file: Path to keywords file
    Returns:
        List[str]: Loaded keywords
    """
    keywords = []
    if not os.path.exists(keywords_file):
        logger.warning(f"Keywords file not found: {keywords_file}")
        return keywords
    try:
        with open(keywords_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                keywords.append(line.lower())
        logger.info(f"Loaded {len(keywords)} keywords from {keywords_file}")
    except Exception as e:
        logger.error(f"Error loading keywords file {keywords_file}: {e}")
    return keywords
class ProviderSpecificFormatter:
    """
    Formats bucket names according to provider-specific rules
    """
    @staticmethod
    def format_for_aws(bucket_name: str) -> str:
        formatted = bucket_name.lower().replace('_', '-')
        formatted = ''.join(c for c in formatted if c.isalnum() or c in '-.')
        formatted = formatted.strip('-.')
        return formatted
    @staticmethod
    def format_for_gcp(bucket_name: str) -> str:
        formatted = bucket_name.lower()
        formatted = ''.join(c for c in formatted if c.isalnum() or c in '-._')
        formatted = formatted.strip('-.')
        return formatted
    @staticmethod
    def format_for_azure(bucket_name: str) -> str:
        formatted = bucket_name.lower().replace('_', '')
        formatted = ''.join(c for c in formatted if c.isalnum() or c == '-')
        formatted = formatted.strip('-')
        if len(formatted) < 3:
            formatted = f"{formatted}001"  # Pad if too short
        elif len(formatted) > 63:
            formatted = formatted[:63]  # Truncate if too long
        return formatted
    @staticmethod
    def format_for_provider(bucket_name: str, provider: str) -> str:
        """
        Format bucket name for specific provider
        Args:
            bucket_name: Original bucket name
            provider: Provider name ('aws', 'gcp', 'azure')
        Returns:
            str: Formatted bucket name
        """
        formatters = {
            'aws': ProviderSpecificFormatter.format_for_aws,
            'gcp': ProviderSpecificFormatter.format_for_gcp,
            'azure': ProviderSpecificFormatter.format_for_azure,
        }
        formatter = formatters.get(provider.lower())
        if formatter:
            return formatter(bucket_name)
        else:
            logger.warning(f"Unknown provider: {provider}")
            return bucket_name.lower()