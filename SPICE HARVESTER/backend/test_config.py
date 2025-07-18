#!/usr/bin/env python3
"""
Test Configuration
Centralized configuration for test endpoints to avoid hardcoded localhost URLs
"""

import os
from typing import Dict, Any


class TestConfig:
    """Centralized test configuration"""
    
    # Default endpoints (can be overridden with environment variables)
    DEFAULT_OMS_BASE_URL = "http://localhost:8000"
    DEFAULT_BFF_BASE_URL = "http://localhost:8002"
    DEFAULT_TERMINUS_URL = "http://localhost:6363"
    
    @classmethod
    def get_oms_base_url(cls) -> str:
        """Get OMS service base URL"""
        return os.getenv("TEST_OMS_URL", cls.DEFAULT_OMS_BASE_URL)
    
    @classmethod
    def get_bff_base_url(cls) -> str:
        """Get BFF service base URL"""
        return os.getenv("TEST_BFF_URL", cls.DEFAULT_BFF_BASE_URL)
    
    @classmethod
    def get_terminus_url(cls) -> str:
        """Get TerminusDB URL"""
        return os.getenv("TEST_TERMINUS_URL", cls.DEFAULT_TERMINUS_URL)
    
    @classmethod
    def get_oms_api_url(cls, path: str = "") -> str:
        """Get OMS API URL with optional path"""
        base = cls.get_oms_base_url()
        return f"{base}/api/v1{path}" if path else f"{base}/api/v1"
    
    @classmethod
    def get_bff_api_url(cls, path: str = "") -> str:
        """Get BFF API URL with optional path"""
        base = cls.get_bff_base_url()
        return f"{base}{path}" if path else base
    
    @classmethod
    def get_database_create_url(cls) -> str:
        """Get database creation endpoint URL"""
        return cls.get_oms_api_url("/database/create")
    
    @classmethod
    def get_database_delete_url(cls, db_name: str) -> str:
        """Get database deletion endpoint URL"""
        return cls.get_oms_api_url(f"/database/{db_name}")
    
    @classmethod
    def get_bff_ontology_url(cls, db_name: str, path: str = "") -> str:
        """Get BFF ontology endpoint URL"""
        base_path = f"/database/{db_name}/ontology"
        full_path = f"{base_path}{path}" if path else base_path
        return cls.get_bff_api_url(full_path)
    
    @classmethod
    def get_oms_ontology_url(cls, db_name: str, path: str = "") -> str:
        """Get OMS ontology endpoint URL"""
        base_path = f"/ontology/{db_name}"
        full_path = f"{base_path}{path}" if path else f"{base_path}/create"
        return cls.get_oms_api_url(full_path)
    
    @classmethod
    def get_test_timeout(cls) -> int:
        """Get test timeout in seconds"""
        return int(os.getenv("TEST_TIMEOUT", "30"))
    
    @classmethod
    def get_test_db_prefix(cls) -> str:
        """Get test database name prefix"""
        return os.getenv("TEST_DB_PREFIX", "test_")
    
    @classmethod
    def is_verbose_logging(cls) -> bool:
        """Check if verbose logging is enabled"""
        return os.getenv("TEST_VERBOSE", "false").lower() == "true"
    
    @classmethod
    def get_all_config(cls) -> Dict[str, Any]:
        """Get all configuration as dictionary"""
        return {
            "oms_base_url": cls.get_oms_base_url(),
            "bff_base_url": cls.get_bff_base_url(),
            "terminus_url": cls.get_terminus_url(),
            "timeout": cls.get_test_timeout(),
            "db_prefix": cls.get_test_db_prefix(),
            "verbose": cls.is_verbose_logging()
        }


# Convenience functions for backwards compatibility
def get_oms_url(path: str = "") -> str:
    """Get OMS URL - convenience function"""
    return TestConfig.get_oms_api_url(path)

def get_bff_url(path: str = "") -> str:
    """Get BFF URL - convenience function"""
    return TestConfig.get_bff_api_url(path)

def get_database_urls(db_name: str) -> Dict[str, str]:
    """Get all database-related URLs for a given database name"""
    return {
        "create": TestConfig.get_database_create_url(),
        "delete": TestConfig.get_database_delete_url(db_name),
        "bff_ontology": TestConfig.get_bff_ontology_url(db_name),
        "oms_ontology": TestConfig.get_oms_ontology_url(db_name)
    }


if __name__ == "__main__":
    """Print current test configuration"""
    import json
    print("Current Test Configuration:")
    print(json.dumps(TestConfig.get_all_config(), indent=2))