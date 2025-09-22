import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cloudvault_discovery.core.config import Config
from cloudvault_discovery.core.permutations import PermutationGenerator
from cloudvault_discovery.core.queue_manager import BucketQueue
from cloudvault_discovery.providers.aws_s3 import AWSS3Worker
from cloudvault_discovery.providers.gcp_storage import GCPStorageWorker
from cloudvault_discovery.providers.azure_blob import AzureBlobWorker
from cloudvault_discovery.core.database import DatabaseTester
# Skip heavy dependencies for basic testing
# from cloudvault_discovery.core.steganography import SteganographyDetector
# from cloudvault_discovery.core.metadata import MetadataExtractor
# from cloudvault_discovery.core.takeover import SubdomainTakeover

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
    
    def test_bucket_queue_init(self):
        from cloudvault_discovery.core.queue_manager import ProviderType
        queue = BucketQueue(ProviderType.AWS)
        self.assertIsNotNone(queue)
    
    def test_providers_init(self):
        # Test provider workers can be imported
        self.assertIsNotNone(AWSS3Worker)
        self.assertIsNotNone(GCPStorageWorker)
        self.assertIsNotNone(AzureBlobWorker)
    
    def test_database_tester(self):
        db_tester = DatabaseTester()
        self.assertIsNotNone(db_tester)
        self.assertIn("mysql", db_tester.default_creds)
        self.assertIn("postgresql", db_tester.default_creds)
    
    # Skipped heavy dependency tests for basic CI
    # def test_steganography_detector(self):
    # def test_metadata_extractor(self):
    # def test_subdomain_takeover(self):
    pass

if __name__ == "__main__":
    unittest.main()
