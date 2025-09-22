import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloudvault_discovery.core.config import Config
from cloudvault_discovery.core.permutations import PermutationGenerator
from cloudvault_discovery.core.queue_manager import QueueManager
from cloudvault_discovery.providers.aws_s3 import AWSS3Provider
from cloudvault_discovery.providers.gcp_storage import GCPStorageProvider
from cloudvault_discovery.providers.azure_blob import AzureBlobProvider
from cloudvault_discovery.core.database import DatabaseTester
from cloudvault_discovery.core.steganography import SteganographyDetector
from cloudvault_discovery.core.metadata import MetadataExtractor
from cloudvault_discovery.core.takeover import SubdomainTakeover

class TestBasicFunctionality(unittest.TestCase):
    def test_config_loading(self):
        config = Config("config.yaml")
        self.assertIsNotNone(config)
        self.assertIn("providers", config.config)
    
    def test_permutation_generator(self):
        gen = PermutationGenerator()
        perms = gen.generate_permutations("example", ["test"])
        self.assertGreater(len(perms), 0)
        self.assertIn("example", perms[0])
    
    def test_queue_manager_init(self):
        config = Config("config.yaml")
        qm = QueueManager(config)
        self.assertIsNotNone(qm)
    
    def test_providers_init(self):
        config = Config("config.yaml")
        
        aws = AWSS3Provider(config.get_provider_config("aws"))
        self.assertIsNotNone(aws)
        
        gcp = GCPStorageProvider(config.get_provider_config("gcp"))
        self.assertIsNotNone(gcp)
        
        azure = AzureBlobProvider(config.get_provider_config("azure"))
        self.assertIsNotNone(azure)
    
    def test_database_tester(self):
        db_tester = DatabaseTester()
        self.assertIsNotNone(db_tester)
        self.assertIn("mysql", db_tester.default_creds)
        self.assertIn("postgresql", db_tester.default_creds)
    
    def test_steganography_detector(self):
        stego = SteganographyDetector()
        self.assertIsNotNone(stego)
        self.assertIn(".png", stego.image_extensions)
    
    def test_metadata_extractor(self):
        meta = MetadataExtractor()
        self.assertIsNotNone(meta)
        self.assertIn(".jpg", meta.extractors)
    
    def test_subdomain_takeover(self):
        takeover = SubdomainTakeover()
        self.assertIsNotNone(takeover)
        self.assertIn("github", takeover.vulnerable_services)

if __name__ == "__main__":
    unittest.main()
