import logging
import requests
import dns.resolver
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class SubdomainTakeover:
    def __init__(self):
        self.vulnerable_services = {
            "github": {
                "cname": ["github.io", "github.com"],
                "response": ["There isn't a GitHub Pages site here"],
                "takeover_possible": True
            },
            "heroku": {
                "cname": ["herokuapp.com"],
                "response": ["No such app", "There's nothing here"],
                "takeover_possible": True
            },
            "s3": {
                "cname": ["s3.amazonaws.com", "s3-website"],
                "response": ["NoSuchBucket", "The specified bucket does not exist"],
                "takeover_possible": True
            },
            "azure": {
                "cname": ["azurewebsites.net", "cloudapp.azure.com", "cloudapp.net"],
                "response": ["404 Web Site not found"],
                "takeover_possible": True
            },
            "shopify": {
                "cname": ["myshopify.com"],
                "response": ["Sorry, this shop is currently unavailable"],
                "takeover_possible": True
            },
            "tumblr": {
                "cname": ["tumblr.com"],
                "response": ["Whatever you were looking for doesn't currently exist"],
                "takeover_possible": True
            },
            "ghost": {
                "cname": ["ghost.io"],
                "response": ["The thing you were looking for is no longer here"],
                "takeover_possible": True
            },
            "surge": {
                "cname": ["surge.sh"],
                "response": ["project not found"],
                "takeover_possible": True
            },
            "bitbucket": {
                "cname": ["bitbucket.io"],
                "response": ["Repository not found"],
                "takeover_possible": True
            },
            "wordpress": {
                "cname": ["wordpress.com"],
                "response": ["Do you want to register"],
                "takeover_possible": True
            },
            "zendesk": {
                "cname": ["zendesk.com"],
                "response": ["Help Center Closed"],
                "takeover_possible": True
            },
            "fastly": {
                "cname": ["fastly.net"],
                "response": ["Fastly error: unknown domain"],
                "takeover_possible": True
            }
        }
        
        self.resolver = dns.resolver.Resolver()
        self.resolver.timeout = 5
        self.resolver.lifetime = 5
    
    def get_cname(self, domain: str) -> Optional[str]:
        try:
            answers = self.resolver.resolve(domain, 'CNAME')
            for rdata in answers:
                return str(rdata.target).rstrip('.')
        except:
            return None
    
    def check_http_response(self, url: str) -> Optional[str]:
        try:
            response = requests.get(url, timeout=10, allow_redirects=False)
            return response.text
        except:
            return None
    
    def detect_vulnerability(self, domain: str) -> Optional[Dict]:
        cname = self.get_cname(domain)
        if not cname:
            return None
        
        for service, config in self.vulnerable_services.items():
            for cname_pattern in config["cname"]:
                if cname_pattern in cname:
                    for protocol in ["http", "https"]:
                        url = f"{protocol}://{domain}"
                        response = self.check_http_response(url)
                        
                        if response:
                            for error_msg in config["response"]:
                                if error_msg.lower() in response.lower():
                                    logger.warning(f"Potential subdomain takeover: {domain} -> {cname} ({service})")
                                    return {
                                        "domain": domain,
                                        "cname": cname,
                                        "service": service,
                                        "vulnerable": True,
                                        "takeover_possible": config["takeover_possible"],
                                        "error_message": error_msg
                                    }
        
        return None
    
    def attempt_takeover(self, vulnerability: Dict) -> bool:
        if not vulnerability["takeover_possible"]:
            return False
        
        service = vulnerability["service"]
        domain = vulnerability["domain"]
        
        if service == "s3":
            return self._takeover_s3(domain)
        elif service == "github":
            return self._takeover_github(domain)
        elif service == "heroku":
            return self._takeover_heroku(domain)
        elif service == "azure":
            return self._takeover_azure(domain)
        
        return False
    
    def _takeover_s3(self, domain: str) -> bool:
        bucket_name = domain.split('.')[0]
        logger.info(f"Attempting S3 takeover for bucket: {bucket_name}")
        return False
    
    def _takeover_github(self, domain: str) -> bool:
        logger.info(f"Attempting GitHub Pages takeover for: {domain}")
        return False
    
    def _takeover_heroku(self, domain: str) -> bool:
        app_name = domain.split('.')[0]
        logger.info(f"Attempting Heroku takeover for app: {app_name}")
        return False
    
    def _takeover_azure(self, domain: str) -> bool:
        logger.info(f"Attempting Azure takeover for: {domain}")
        return False
    
    def scan_bucket_for_takeover(self, bucket_url: str) -> List[Dict]:
        vulnerabilities = []
        
        parsed = urlparse(bucket_url)
        base_domain = parsed.hostname
        
        if base_domain:
            vuln = self.detect_vulnerability(base_domain)
            if vuln:
                vulnerabilities.append(vuln)
        
        potential_subdomains = [
            f"www.{base_domain}",
            f"api.{base_domain}",
            f"admin.{base_domain}",
            f"app.{base_domain}",
            f"cdn.{base_domain}",
            f"static.{base_domain}"
        ]
        
        for subdomain in potential_subdomains:
            vuln = self.detect_vulnerability(subdomain)
            if vuln:
                vulnerabilities.append(vuln)
        
        return vulnerabilities