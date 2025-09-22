import logging
import socket
import paramiko
import pymongo
import psycopg2
import mysql.connector
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

class DatabaseTester:
    def __init__(self, wordlist_path: Optional[str] = None):
        self.default_creds = {
            "mysql": [
                ("root", ""),
                ("root", "root"),
                ("root", "password"),
                ("root", "123456"),
                ("root", "admin"),
                ("mysql", "mysql"),
                ("admin", "admin")
            ],
            "postgresql": [
                ("postgres", ""),
                ("postgres", "postgres"),
                ("postgres", "password"),
                ("postgres", "admin"),
                ("postgres", "123456")
            ],
            "mongodb": [
                ("", ""),
                ("admin", "admin"),
                ("root", "root"),
                ("mongo", "mongo")
            ],
            "redis": [
                ("", ""),
                ("redis", "redis"),
                ("default", "")
            ],
            "mssql": [
                ("sa", ""),
                ("sa", "sa"),
                ("sa", "password"),
                ("sa", "Password123!")
            ]
        }
        
        if wordlist_path:
            self.load_wordlist(wordlist_path)
        
        self.common_ports = {
            "mysql": [3306, 3307],
            "postgresql": [5432, 5433],
            "mongodb": [27017, 27018, 27019],
            "redis": [6379, 6380],
            "mssql": [1433, 1434],
            "cassandra": [9042],
            "elasticsearch": [9200, 9300]
        }
        
        self.common_users = {
            "mysql": ["root", "mysql", "admin", "user", "test", "web", "db"],
            "postgresql": ["postgres", "admin", "user", "test", "db"],
            "mongodb": ["admin", "root", "mongo", "user"],
            "mssql": ["sa", "admin", "sql", "user"]
        }
    
    def load_wordlist(self, wordlist_path: str):
        try:
            with open(wordlist_path, 'r') as f:
                passwords = [line.strip() for line in f if line.strip()]
            
            for db_type in self.default_creds:
                users = self.common_users.get(db_type, ["admin", "root"])
                for user in users:
                    for password in passwords[:100]:  # Limit to first 100 passwords
                        self.default_creds[db_type].append((user, password))
            
            logger.info(f"Loaded {len(passwords)} passwords from wordlist")
            
        except Exception as e:
            logger.error(f"Failed to load wordlist: {e}")
    
    def test_mysql(self, host: str, port: int = 3306) -> List[Tuple[str, str]]:
        valid_creds = []
        for username, password in self.default_creds["mysql"]:
            try:
                conn = mysql.connector.connect(
                    host=host,
                    port=port,
                    user=username,
                    password=password,
                    connection_timeout=5
                )
                conn.close()
                valid_creds.append((username, password))
                logger.warning(f"Found MySQL default creds: {username}:{password} on {host}:{port}")
            except:
                pass
        return valid_creds
    
    def test_postgresql(self, host: str, port: int = 5432) -> List[Tuple[str, str]]:
        valid_creds = []
        for username, password in self.default_creds["postgresql"]:
            try:
                conn = psycopg2.connect(
                    host=host,
                    port=port,
                    user=username,
                    password=password,
                    connect_timeout=5
                )
                conn.close()
                valid_creds.append((username, password))
                logger.warning(f"Found PostgreSQL default creds: {username}:{password} on {host}:{port}")
            except:
                pass
        return valid_creds
    
    def test_mongodb(self, host: str, port: int = 27017) -> List[Tuple[str, str]]:
        valid_creds = []
        for username, password in self.default_creds["mongodb"]:
            try:
                if username and password:
                    uri = f"mongodb://{username}:{password}@{host}:{port}/"
                else:
                    uri = f"mongodb://{host}:{port}/"
                
                client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
                client.admin.command('ping')
                client.close()
                valid_creds.append((username, password))
                logger.warning(f"Found MongoDB default creds: {username}:{password} on {host}:{port}")
            except:
                pass
        return valid_creds
    
    def scan_database_ports(self, host: str) -> Dict[str, List[int]]:
        open_ports = {}
        
        for db_type, ports in self.common_ports.items():
            open_ports[db_type] = []
            for port in ports:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((host, port))
                sock.close()
                if result == 0:
                    open_ports[db_type].append(port)
                    logger.info(f"Found open {db_type} port {port} on {host}")
        
        return open_ports
    
    def test_all_databases(self, host: str) -> Dict[str, List[Tuple[str, str]]]:
        results = {}
        open_ports = self.scan_database_ports(host)
        
        if open_ports.get("mysql"):
            for port in open_ports["mysql"]:
                creds = self.test_mysql(host, port)
                if creds:
                    results[f"mysql:{port}"] = creds
        
        if open_ports.get("postgresql"):
            for port in open_ports["postgresql"]:
                creds = self.test_postgresql(host, port)
                if creds:
                    results[f"postgresql:{port}"] = creds
        
        if open_ports.get("mongodb"):
            for port in open_ports["mongodb"]:
                creds = self.test_mongodb(host, port)
                if creds:
                    results[f"mongodb:{port}"] = creds
        
        return results