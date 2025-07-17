"""
URL Standardization Strategy for SPICE HARVESTER
Provides consistent URL patterns and validation across all services
"""

import re
from typing import Dict, List, Optional, Union
from enum import Enum
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """Service types for URL standardization"""
    BFF = "bff"
    OMS = "oms"
    TERMINUSDB = "terminusdb"
    EXTERNAL = "external"


class URLPattern(Enum):
    """Standardized URL patterns"""
    # Health and status
    HEALTH = "/health"
    ROOT = "/"
    STATUS = "/status"
    METRICS = "/metrics"
    
    # API versioning
    API_V1 = "/api/v1"
    API_V2 = "/api/v2"
    
    # Resource patterns
    DATABASES = "/databases"
    DATABASE_ITEM = "/database/{db_name}"
    ONTOLOGIES = "/ontologies"
    ONTOLOGY_ITEM = "/ontology/{ontology_id}"
    
    # Branch operations
    BRANCHES = "/branches"
    BRANCH_ITEM = "/branch/{branch_name}"
    BRANCH_CREATE = "/database/{db_name}/branch"
    BRANCH_CHECKOUT = "/database/{db_name}/checkout"
    BRANCH_MERGE = "/database/{db_name}/merge"
    BRANCH_ROLLBACK = "/database/{db_name}/rollback"
    
    # Query operations
    QUERY = "/database/{db_name}/query"
    QUERY_STRUCTURED = "/database/{db_name}/query/structured"
    
    # Mapping operations
    MAPPINGS = "/database/{db_name}/mappings"
    MAPPINGS_IMPORT = "/database/{db_name}/mappings/import"
    MAPPINGS_EXPORT = "/database/{db_name}/mappings/export"


@dataclass
class ServiceEndpoint:
    """Service endpoint configuration"""
    service_type: ServiceType
    base_url: str
    api_version: str = "v1"
    default_port: int = 8000
    health_path: str = "/health"
    
    def get_full_url(self, path: str = "") -> str:
        """Get full URL for a given path"""
        return f"{self.base_url.rstrip('/')}{path}"
    
    def get_api_url(self, path: str = "") -> str:
        """Get API URL with version"""
        api_base = f"/api/{self.api_version}"
        return f"{self.base_url.rstrip('/')}{api_base}{path}"


class URLStandardizer:
    """
    URL standardization and validation utility
    
    Features:
    - Consistent URL patterns across services
    - URL validation and normalization
    - Service endpoint discovery
    - API versioning support
    """
    
    def __init__(self):
        self.service_endpoints = self._define_service_endpoints()
        self.url_patterns = self._define_url_patterns()
    
    def _define_service_endpoints(self) -> Dict[str, ServiceEndpoint]:
        """Define all service endpoints"""
        return {
            "bff": ServiceEndpoint(
                service_type=ServiceType.BFF,
                base_url="http://localhost:8002",
                api_version="v1",
                default_port=8002,
                health_path="/health"
            ),
            "oms": ServiceEndpoint(
                service_type=ServiceType.OMS,
                base_url="http://localhost:8000",
                api_version="v1", 
                default_port=8000,
                health_path="/health"
            ),
            "terminusdb": ServiceEndpoint(
                service_type=ServiceType.TERMINUSDB,
                base_url="http://localhost:6363",
                api_version="",
                default_port=6363,
                health_path="/api/ok"
            )
        }
    
    def _define_url_patterns(self) -> Dict[str, Dict[str, str]]:
        """Define URL patterns for different operations"""
        return {
            # BFF Service URLs
            "bff": {
                "root": "/",
                "health": "/health",
                "databases_list": "/api/v1/databases",
                "database_create": "/api/v1/database",
                "database_item": "/api/v1/database/{db_name}",
                "ontology_create": "/database/{db_name}/ontology",
                "ontology_list": "/database/{db_name}/ontologies",
                "ontology_item": "/database/{db_name}/ontology/{ontology_id}",
                "query": "/database/{db_name}/query",
                "query_structured": "/database/{db_name}/query/structured",
                "branch_create": "/database/{db_name}/branch",
                "branch_checkout": "/database/{db_name}/checkout", 
                "branch_merge": "/database/{db_name}/merge",
                "branch_rollback": "/database/{db_name}/rollback",
                "mappings": "/database/{db_name}/mappings",
                "mappings_import": "/database/{db_name}/mappings/import",
                "mappings_export": "/database/{db_name}/mappings/export"
            },
            
            # OMS Service URLs
            "oms": {
                "root": "/",
                "health": "/health",
                "databases_list": "/api/v1/databases",
                "database_create": "/api/v1/database/create",
                "database_delete": "/api/v1/database/{db_name}",
                "ontology_create": "/api/v1/database/{db_name}/ontology",
                "ontology_list": "/api/v1/database/{db_name}/ontologies",
                "ontology_get": "/api/v1/database/{db_name}/ontology/{ontology_id}",
                "ontology_update": "/api/v1/database/{db_name}/ontology/{ontology_id}",
                "ontology_delete": "/api/v1/database/{db_name}/ontology/{ontology_id}",
                "branch_create": "/api/v1/database/{db_name}/branch",
                "branch_list": "/api/v1/database/{db_name}/branches",
                "version_create": "/api/v1/database/{db_name}/version"
            },
            
            # TerminusDB URLs
            "terminusdb": {
                "root": "/",
                "health": "/api/ok",
                "info": "/api/info",
                "database_create": "/api/db/{organization}/{database}",
                "database_delete": "/api/db/{organization}/{database}",
                "document_insert": "/api/document/{organization}/{database}",
                "document_get": "/api/document/{organization}/{database}",
                "woql_query": "/api/woql/{organization}/{database}",
                "branch_create": "/api/branch/{organization}/{database}",
                "graph_query": "/api/graphql/{organization}/{database}"
            }
        }
    
    def get_service_url(self, service: str, operation: str, **kwargs) -> str:
        """Get standardized URL for a service operation"""
        if service not in self.url_patterns:
            raise ValueError(f"Unknown service: {service}")
        
        if operation not in self.url_patterns[service]:
            raise ValueError(f"Unknown operation '{operation}' for service '{service}'")
        
        url_template = self.url_patterns[service][operation]
        
        # Replace placeholders with actual values
        try:
            return url_template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing required parameter for URL: {e}")
    
    def get_full_service_url(self, service: str, operation: str, **kwargs) -> str:
        """Get full URL including service base URL"""
        if service not in self.service_endpoints:
            raise ValueError(f"Unknown service endpoint: {service}")
        
        endpoint = self.service_endpoints[service]
        relative_url = self.get_service_url(service, operation, **kwargs)
        
        return endpoint.get_full_url(relative_url)
    
    def validate_url(self, url: str) -> bool:
        """Validate URL format and structure"""
        # Basic URL validation
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(url):
            return False
        
        # Check for suspicious patterns
        suspicious_patterns = [
            r'\.\./',  # Path traversal
            r'javascript:',  # JavaScript injection
            r'<script',  # XSS
            r'%2e%2e%2f',  # Encoded path traversal
        ]
        
        for pattern in suspicious_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                logger.warning(f"Suspicious pattern detected in URL: {pattern}")
                return False
        
        return True
    
    def normalize_url(self, url: str) -> str:
        """Normalize URL format"""
        # Remove trailing slashes except for root
        if url != "/" and url.endswith("/"):
            url = url.rstrip("/")
        
        # Ensure lowercase for consistency (except path parameters)
        parts = url.split("?")
        path = parts[0]
        query = "?" + parts[1] if len(parts) > 1 else ""
        
        # Normalize path but preserve case in query parameters
        normalized_path = path.lower()
        
        return normalized_path + query
    
    def extract_path_parameters(self, url_template: str, actual_url: str) -> Dict[str, str]:
        """Extract path parameters from URL"""
        # Convert template to regex pattern
        pattern = url_template
        params = {}
        
        # Find all {param_name} patterns
        param_matches = re.findall(r'\{([^}]+)\}', url_template)
        
        if not param_matches:
            return params
        
        # Replace {param} with regex groups
        regex_pattern = pattern
        for param in param_matches:
            regex_pattern = regex_pattern.replace(f"{{{param}}}", r'([^/]+)')
        
        # Match against actual URL
        match = re.match(regex_pattern, actual_url)
        if match:
            for i, param in enumerate(param_matches):
                params[param] = match.group(i + 1)
        
        return params
    
    def build_query_string(self, params: Dict[str, Union[str, int, bool]]) -> str:
        """Build query string from parameters"""
        if not params:
            return ""
        
        query_parts = []
        for key, value in params.items():
            if value is not None:
                # Convert boolean to lowercase string
                if isinstance(value, bool):
                    value = str(value).lower()
                query_parts.append(f"{key}={value}")
        
        return "?" + "&".join(query_parts) if query_parts else ""
    
    def get_service_health_urls(self) -> Dict[str, str]:
        """Get health check URLs for all services"""
        health_urls = {}
        
        for service_name, endpoint in self.service_endpoints.items():
            health_urls[service_name] = endpoint.get_full_url(endpoint.health_path)
        
        return health_urls
    
    def get_cross_service_mapping(self) -> Dict[str, Dict[str, str]]:
        """Get mapping of equivalent operations across services"""
        return {
            "database_create": {
                "bff": "/api/v1/database",
                "oms": "/api/v1/database/create",
                "terminusdb": "/api/db/{organization}/{database}"
            },
            "ontology_create": {
                "bff": "/database/{db_name}/ontology",
                "oms": "/api/v1/database/{db_name}/ontology"
            },
            "health_check": {
                "bff": "/health",
                "oms": "/health", 
                "terminusdb": "/api/ok"
            }
        }
    
    def validate_cross_service_consistency(self) -> List[str]:
        """Validate URL consistency across services"""
        issues = []
        
        # Check for common operations that should have similar patterns
        common_operations = ["health", "root"]
        
        for operation in common_operations:
            patterns = []
            for service, urls in self.url_patterns.items():
                if operation in urls:
                    patterns.append((service, urls[operation]))
            
            # Check for inconsistencies (basic check)
            if len(set(pattern[1] for pattern in patterns)) > 1:
                issue = f"Inconsistent URL patterns for '{operation}': {patterns}"
                issues.append(issue)
                logger.warning(issue)
        
        return issues


# Global instance
url_standardizer = URLStandardizer()


# Convenience functions
def get_service_url(service: str, operation: str, **kwargs) -> str:
    """Get standardized URL for a service operation"""
    return url_standardizer.get_service_url(service, operation, **kwargs)


def get_full_service_url(service: str, operation: str, **kwargs) -> str:
    """Get full URL including service base URL"""
    return url_standardizer.get_full_service_url(service, operation, **kwargs)


def validate_url(url: str) -> bool:
    """Validate URL format and security"""
    return url_standardizer.validate_url(url)


def normalize_url(url: str) -> str:
    """Normalize URL format"""
    return url_standardizer.normalize_url(url)


def get_health_urls() -> Dict[str, str]:
    """Get health check URLs for all services"""
    return url_standardizer.get_service_health_urls()


# URL constants for common operations
class URLs:
    """URL constants for common operations"""
    
    # BFF URLs
    BFF_HEALTH = "/health"
    BFF_ROOT = "/"
    BFF_DATABASES = "/api/v1/databases"
    BFF_DATABASE_CREATE = "/api/v1/database"
    
    # OMS URLs  
    OMS_HEALTH = "/health"
    OMS_DATABASES = "/api/v1/databases"
    OMS_DATABASE_CREATE = "/api/v1/database/create"
    
    # TerminusDB URLs
    TERMINUSDB_HEALTH = "/api/ok"
    TERMINUSDB_INFO = "/api/info"
    
    # Template URLs (with placeholders)
    class Templates:
        DATABASE_ITEM = "/database/{db_name}"
        ONTOLOGY_ITEM = "/database/{db_name}/ontology/{ontology_id}"
        BRANCH_OPERATION = "/database/{db_name}/{operation}"
        MAPPING_OPERATION = "/database/{db_name}/mappings/{operation}"


if __name__ == "__main__":
    # Test URL standardization
    standardizer = URLStandardizer()
    
    # Test URL generation
    print("BFF Health URL:", get_full_service_url("bff", "health"))
    print("OMS Database Create URL:", get_full_service_url("oms", "database_create"))
    print("BFF Ontology URL:", get_service_url("bff", "ontology_create", db_name="test_db"))
    
    # Test validation
    print("Valid URL:", validate_url("http://localhost:8002/health"))
    print("Invalid URL:", validate_url("javascript:alert('xss')"))
    
    # Test consistency
    issues = standardizer.validate_cross_service_consistency()
    if issues:
        print("Consistency issues found:", issues)
    else:
        print("URL patterns are consistent")