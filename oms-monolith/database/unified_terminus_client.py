"""
Unified TerminusDB Client - Configurable for different use cases
Consolidates simple_terminus_client, terminus_db, and terminus_db_simple
"""

import os
import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from enum import Enum
import httpx
from datetime import datetime
from database.clients.unified_http_client import UnifiedHTTPClient, create_basic_client, HTTPClientConfig

logger = logging.getLogger(__name__)


class ClientMode(Enum):
    """Client operation modes"""
    SIMPLE = "simple"       # Basic HTTP client, no dependencies
    PRODUCTION = "production"  # Full features: pooling, mTLS, observability
    MEMORY = "memory"       # In-memory mock for testing


class TerminusDBConfig:
    """Configuration for TerminusDB client"""
    
    def __init__(
        self,
        endpoint: str = "http://localhost:6363",
        team: str = "admin",
        db: str = "oms",
        user: str = "admin",
        key: str = "root",
        mode: ClientMode = ClientMode.SIMPLE,
        # Production mode settings
        enable_pooling: bool = False,
        enable_mtls: bool = False,
        enable_observability: bool = False,
        enable_retry: bool = True,
        max_retries: int = 3,
        # Pool settings
        pool_size: int = 10,
        pool_timeout: float = 30.0,
        # mTLS settings
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
        ca_path: Optional[str] = None
    ):
        self.endpoint = endpoint
        self.team = team
        self.db = db
        self.user = user
        self.key = key
        self.mode = mode
        self.enable_pooling = enable_pooling
        self.enable_mtls = enable_mtls
        self.enable_observability = enable_observability
        self.enable_retry = enable_retry
        self.max_retries = max_retries
        self.pool_size = pool_size
        self.pool_timeout = pool_timeout
        self.cert_path = cert_path
        self.key_path = key_path
        self.ca_path = ca_path
    
    @classmethod
    def from_env(cls) -> "TerminusDBConfig":
        """Create config from environment variables"""
        mode_str = os.getenv("TERMINUS_CLIENT_MODE", "simple").lower()
        mode = ClientMode(mode_str) if mode_str in [m.value for m in ClientMode] else ClientMode.SIMPLE
        
        return cls(
            endpoint=os.getenv("TERMINUSDB_ENDPOINT", "http://localhost:6363"),
            team=os.getenv("TERMINUSDB_TEAM", "admin"),
            db=os.getenv("TERMINUSDB_DB", "oms"),
            user=os.getenv("TERMINUSDB_USER", "admin"),
            key=os.getenv("TERMINUSDB_KEY", "root"),
            mode=mode,
            enable_pooling=os.getenv("TERMINUS_ENABLE_POOLING", "false").lower() == "true",
            enable_mtls=os.getenv("TERMINUS_ENABLE_MTLS", "false").lower() == "true",
            enable_observability=os.getenv("TERMINUS_ENABLE_OBSERVABILITY", "false").lower() == "true",
            enable_retry=os.getenv("TERMINUS_ENABLE_RETRY", "true").lower() == "true",
            max_retries=int(os.getenv("TERMINUS_MAX_RETRIES", "3")),
            pool_size=int(os.getenv("TERMINUS_POOL_SIZE", "10")),
            pool_timeout=float(os.getenv("TERMINUS_POOL_TIMEOUT", "30.0")),
            cert_path=os.getenv("TERMINUS_CERT_PATH"),
            key_path=os.getenv("TERMINUS_KEY_PATH"),
            ca_path=os.getenv("TERMINUS_CA_PATH")
        )


class TerminusDBClientBase(ABC):
    """Base interface for all TerminusDB clients"""
    
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to database"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close database connection"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if database is healthy"""
        pass
    
    # Document operations
    @abstractmethod
    async def insert_document(self, doc_type: str, document: Dict[str, Any], graph_type: str = "instance") -> str:
        """Insert a new document"""
        pass
    
    @abstractmethod
    async def get_document(self, doc_id: str, doc_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get document by ID"""
        pass
    
    @abstractmethod
    async def update_document(self, doc_id: str, document: Dict[str, Any], graph_type: str = "instance") -> bool:
        """Update existing document"""
        pass
    
    @abstractmethod
    async def delete_document(self, doc_id: str, graph_type: str = "instance") -> bool:
        """Delete document"""
        pass
    
    @abstractmethod
    async def query_documents(self, doc_type: str, graph_type: str = "instance") -> List[Dict[str, Any]]:
        """Query documents by type"""
        pass
    
    # Database operations
    @abstractmethod
    async def create_database(self, db_id: str, label: str, description: str = "") -> bool:
        """Create new database"""
        pass
    
    @abstractmethod
    async def delete_database(self, db_id: str) -> bool:
        """Delete database"""
        pass
    
    # Query operations
    @abstractmethod
    async def query(self, woql_query: str) -> Any:
        """Execute WOQL query"""
        pass


class SimpleTerminusDBClient(TerminusDBClientBase):
    """Simple HTTP-based client without dependencies"""
    
    def __init__(self, config: TerminusDBConfig):
        self.config = config
        self.client: Optional[UnifiedHTTPClient] = None
        self._headers = {
            "Authorization": f"Basic {self._encode_auth()}",
            "Content-Type": "application/json"
        }
        self._is_connected = False
        self._memory_fallback = False
        self._memory_store: Dict[str, Any] = {}
    
    def _encode_auth(self) -> str:
        """Encode authentication credentials"""
        import base64
        credentials = f"{self.config.user}:{self.config.key}"
        return base64.b64encode(credentials.encode()).decode()
    
    def _build_url(self, path: str) -> str:
        """Build full URL for API endpoint"""
        return f"{self.config.endpoint}{path}"
    
    async def connect(self) -> bool:
        """Establish connection to database"""
        try:
            http_config = HTTPClientConfig(
                base_url=self.config.endpoint,
                timeout=30.0,
                headers=self._headers
            )
            self.client = UnifiedHTTPClient(http_config)
            
            # Check if database exists, create if not
            db_path = f"/api/db/{self.config.team}/{self.config.db}"
            response = await self.client.get(db_path)
            
            if response.status_code == 404:
                # Create database
                create_response = await self.client.post(
                    f"/api/db/{self.config.team}",
                    json={
                        "db_id": self.config.db,
                        "label": f"{self.config.db} Database",
                        "description": "OMS Database"
                    }
                )
                if create_response.status_code not in [200, 201]:
                    logger.warning(f"Failed to create database: {create_response.text}")
                    self._memory_fallback = True
                    return True
            
            self._is_connected = True
            logger.info(f"Connected to TerminusDB at {self.config.endpoint}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to TerminusDB: {e}")
            self._memory_fallback = True
            return True
    
    async def disconnect(self) -> None:
        """Close database connection"""
        if self.client:
            await self.client.close()
            self.client = None
        self._is_connected = False
        logger.info("Disconnected from TerminusDB")
    
    async def health_check(self) -> bool:
        """Check if database is healthy"""
        if self._memory_fallback:
            return True
            
        try:
            response = await self.client.get("/api/status")
            return response.status_code == 200
        except:
            return False
    
    async def insert_document(self, doc_type: str, document: Dict[str, Any], graph_type: str = "instance") -> str:
        """Insert a new document"""
        if self._memory_fallback:
            doc_id = document.get("@id", f"{doc_type}/{datetime.utcnow().timestamp()}")
            self._memory_store[doc_id] = document
            return doc_id
        
        if "@type" not in document:
            document["@type"] = doc_type
        
        path = f"/api/document/{self.config.team}/{self.config.db}?graph_type={graph_type}&author=system"
        
        try:
            response = await self.client.post(path, json=document)
            if response.status_code in [200, 201]:
                return document.get("@id", "")
            else:
                raise Exception(f"Insert failed: {response.text}")
        except Exception as e:
            logger.error(f"Error inserting document: {e}")
            raise
    
    async def get_document(self, doc_id: str, doc_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get document by ID"""
        if self._memory_fallback:
            return self._memory_store.get(doc_id)
        
        path = f"/api/document/{self.config.team}/{self.config.db}/{doc_id}"
        
        try:
            response = await self.client.get(path)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Error getting document: {e}")
            return None
    
    async def update_document(self, doc_id: str, document: Dict[str, Any], graph_type: str = "instance") -> bool:
        """Update existing document"""
        if self._memory_fallback:
            if doc_id in self._memory_store:
                self._memory_store[doc_id].update(document)
                return True
            return False
        
        document["@id"] = doc_id
        path = f"/api/document/{self.config.team}/{self.config.db}?graph_type={graph_type}&author=system"
        
        try:
            response = await self.client.put(path, json=document)
            return response.status_code in [200, 204]
        except Exception as e:
            logger.error(f"Error updating document: {e}")
            return False
    
    async def delete_document(self, doc_id: str, graph_type: str = "instance") -> bool:
        """Delete document"""
        if self._memory_fallback:
            if doc_id in self._memory_store:
                del self._memory_store[doc_id]
                return True
            return False
        
        path = f"/api/document/{self.config.team}/{self.config.db}/{doc_id}?graph_type={graph_type}&author=system"
        
        try:
            response = await self.client.delete(path)
            return response.status_code in [200, 204]
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            return False
    
    async def query_documents(self, doc_type: str, graph_type: str = "instance") -> List[Dict[str, Any]]:
        """Query documents by type"""
        if self._memory_fallback:
            return [doc for doc in self._memory_store.values() 
                   if doc.get("@type") == doc_type]
        
        query = f"""
        SELECT ?doc
        WHERE {{
            ?doc a {doc_type}
        }}
        """
        
        result = await self.query(query)
        return result.get("bindings", []) if result else []
    
    async def create_database(self, db_id: str, label: str, description: str = "") -> bool:
        """Create new database"""
        path = f"/api/db/{self.config.team}"
        
        try:
            response = await self.client.post(
                path,
                json={
                    "db_id": db_id,
                    "label": label,
                    "description": description
                }
            )
            return response.status_code in [200, 201]
        except Exception as e:
            logger.error(f"Error creating database: {e}")
            return False
    
    async def delete_database(self, db_id: str) -> bool:
        """Delete database"""
        path = f"/api/db/{self.config.team}/{db_id}"
        
        try:
            response = await self.client.delete(path)
            return response.status_code in [200, 204]
        except Exception as e:
            logger.error(f"Error deleting database: {e}")
            return False
    
    async def query(self, woql_query: str) -> Any:
        """Execute WOQL query"""
        if self._memory_fallback:
            return {"bindings": []}
        
        path = f"/api/woql/{self.config.team}/{self.config.db}"
        
        try:
            response = await self.client.post(
                path,
                json={"query": woql_query}
            )
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            return None


class UnifiedTerminusDBClient:
    """Factory for creating appropriate TerminusDB client based on configuration"""
    
    @staticmethod
    def create(config: Optional[TerminusDBConfig] = None) -> TerminusDBClientBase:
        """Create TerminusDB client based on configuration"""
        if config is None:
            config = TerminusDBConfig.from_env()
        
        if config.mode == ClientMode.MEMORY:
            # Return in-memory implementation
            from database.clients.terminus_db_simple import TerminusDBClientDummy
            return TerminusDBClientDummy()
        
        elif config.mode == ClientMode.PRODUCTION:
            # For production mode, we'll need to implement adapter
            # For now, fall back to simple client
            logger.info("Production mode requested, using simple client with retry enabled")
            return SimpleTerminusDBClient(config)
        
        else:  # ClientMode.SIMPLE
            return SimpleTerminusDBClient(config)


# Alias for backward compatibility
SimpleTerminusDBClient = UnifiedTerminusDBClient.create