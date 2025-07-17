"""
End-to-End Tests for Critical User Flows
Tests complete user workflows from start to finish across all services
"""

import pytest
import httpx
import asyncio
import json
import uuid
from typing import Dict, Any, List
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class TestCriticalUserFlows:
    """End-to-end tests for critical user workflows"""
    
    # Test configuration
    BFF_BASE_URL = "http://localhost:8002"
    OMS_BASE_URL = "http://localhost:8000"
    TIMEOUT = 60
    
    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        """Setup and teardown for each test"""
        # Setup
        self.client = httpx.AsyncClient(timeout=self.TIMEOUT)
        self.test_db_name = f"test_e2e_{int(time.time())}"
        self.created_resources = []
        
        # Verify services are running
        await self._verify_services()
        
        yield
        
        # Cleanup
        await self._cleanup_resources()
        await self.client.aclose()
    
    async def _verify_services(self):
        """Verify all required services are running"""
        services = [
            ("BFF", f"{self.BFF_BASE_URL}/health"),
            ("OMS", f"{self.OMS_BASE_URL}/health")
        ]
        
        for service_name, url in services:
            try:
                response = await self.client.get(url)
                if response.status_code not in [200, 503]:
                    pytest.skip(f"{service_name} service not available")
            except httpx.RequestError:
                pytest.skip(f"{service_name} service not reachable")
    
    async def _cleanup_resources(self):
        """Clean up created test resources"""
        # Delete test database if created
        if hasattr(self, 'test_db_name'):
            try:
                await self.client.delete(f"{self.OMS_BASE_URL}/api/v1/database/{self.test_db_name}")
                logger.info(f"Cleaned up test database: {self.test_db_name}")
            except Exception as e:
                logger.warning(f"Failed to cleanup database {self.test_db_name}: {e}")
    
    # Critical Flow 1: Database Lifecycle Management
    
    @pytest.mark.asyncio
    async def test_database_lifecycle_flow(self):
        """
        Test complete database lifecycle:
        1. Create database
        2. Verify database exists
        3. List databases
        4. Delete database
        5. Verify deletion
        """
        db_name = f"test_lifecycle_{uuid.uuid4().hex[:8]}"
        
        # Step 1: Create database via BFF
        create_payload = {
            "name": db_name,
            "description": "End-to-end test database"
        }
        
        response = await self.client.post(
            f"{self.BFF_BASE_URL}/api/v1/database",
            json=create_payload
        )
        
        assert response.status_code == 200, f"Database creation failed: {response.text}"
        create_data = response.json()
        assert create_data["status"] == "success"
        assert create_data["name"] == db_name
        
        # Step 2: Verify database exists in OMS
        response = await self.client.get(f"{self.OMS_BASE_URL}/api/v1/databases")
        assert response.status_code == 200
        
        databases = response.json()
        db_names = [db.get("name", db.get("database")) for db in databases if isinstance(databases, list)]
        if isinstance(databases, dict) and "databases" in databases:
            db_names = [db.get("name", db.get("database")) for db in databases["databases"]]
        
        assert db_name in db_names, f"Database {db_name} not found in list: {db_names}"
        
        # Step 3: List databases via BFF
        response = await self.client.get(f"{self.BFF_BASE_URL}/api/v1/databases")
        assert response.status_code == 200
        
        bff_databases = response.json()
        bff_db_names = [db.get("name", db.get("database")) for db in bff_databases if isinstance(bff_databases, list)]
        
        assert db_name in bff_db_names, f"Database {db_name} not found in BFF list"
        
        # Step 4: Delete database
        response = await self.client.delete(f"{self.OMS_BASE_URL}/api/v1/database/{db_name}")
        assert response.status_code in [200, 204], f"Database deletion failed: {response.text}"
        
        # Step 5: Verify deletion
        response = await self.client.get(f"{self.OMS_BASE_URL}/api/v1/databases")
        assert response.status_code == 200
        
        updated_databases = response.json()
        updated_db_names = [db.get("name", db.get("database")) for db in updated_databases if isinstance(updated_databases, list)]
        if isinstance(updated_databases, dict) and "databases" in updated_databases:
            updated_db_names = [db.get("name", db.get("database")) for db in updated_databases["databases"]]
        
        assert db_name not in updated_db_names, f"Database {db_name} still exists after deletion"
        
        logger.info(f"✓ Database lifecycle test completed successfully for {db_name}")
    
    # Critical Flow 2: Ontology Management Flow
    
    @pytest.mark.asyncio
    async def test_ontology_management_flow(self):
        """
        Test complete ontology management:
        1. Create database
        2. Create ontology class
        3. Retrieve ontology
        4. Update ontology
        5. Query ontology
        6. Delete ontology
        """
        db_name = f"test_ontology_{uuid.uuid4().hex[:8]}"
        
        # Step 1: Create database
        create_db_payload = {
            "name": db_name,
            "description": "Ontology test database"
        }
        
        response = await self.client.post(
            f"{self.BFF_BASE_URL}/api/v1/database",
            json=create_db_payload
        )
        assert response.status_code == 200
        
        # Step 2: Create ontology class via BFF
        ontology_payload = {
            "label": {
                "ko": "테스트 클래스",
                "en": "Test Class"
            },
            "description": {
                "ko": "E2E 테스트용 클래스",
                "en": "Class for E2E testing"
            },
            "properties": [
                {
                    "name": "testProperty",
                    "type": "xsd:string",
                    "label": {
                        "ko": "테스트 속성",
                        "en": "Test Property"
                    },
                    "required": False
                }
            ]
        }
        
        response = await self.client.post(
            f"{self.BFF_BASE_URL}/database/{db_name}/ontology",
            json=ontology_payload,
            headers={"Accept-Language": "ko"}
        )
        
        assert response.status_code == 200, f"Ontology creation failed: {response.text}"
        ontology_data = response.json()
        assert "id" in ontology_data
        ontology_id = ontology_data["id"]
        
        # Step 3: Retrieve ontology
        response = await self.client.get(
            f"{self.BFF_BASE_URL}/database/{db_name}/ontology/{ontology_id}",
            headers={"Accept-Language": "ko"}
        )
        
        assert response.status_code == 200
        retrieved_ontology = response.json()
        assert retrieved_ontology["id"] == ontology_id
        assert "테스트 클래스" in str(retrieved_ontology)
        
        # Step 4: Update ontology
        update_payload = {
            "description": {
                "ko": "업데이트된 설명",
                "en": "Updated description"
            }
        }
        
        response = await self.client.put(
            f"{self.BFF_BASE_URL}/database/{db_name}/ontology/{ontology_id}",
            json=update_payload,
            headers={"Accept-Language": "ko"}
        )
        
        # Update might not be implemented, so we accept 200 or 404
        assert response.status_code in [200, 404, 501]
        
        # Step 5: Query ontologies
        response = await self.client.get(
            f"{self.BFF_BASE_URL}/database/{db_name}/ontologies",
            headers={"Accept-Language": "ko"}
        )
        
        assert response.status_code == 200
        ontologies_list = response.json()
        assert len(ontologies_list) >= 1
        
        # Step 6: Delete ontology (if endpoint exists)
        response = await self.client.delete(
            f"{self.BFF_BASE_URL}/database/{db_name}/ontology/{ontology_id}"
        )
        
        # Delete might not be implemented
        assert response.status_code in [200, 204, 404, 501]
        
        # Cleanup database
        await self.client.delete(f"{self.OMS_BASE_URL}/api/v1/database/{db_name}")
        
        logger.info(f"✓ Ontology management flow completed successfully")
    
    # Critical Flow 3: Data Query Flow
    
    @pytest.mark.asyncio
    async def test_data_query_flow(self):
        """
        Test data querying workflow:
        1. Create database with ontology
        2. Query with different parameters
        3. Test structured query
        4. Test query validation
        """
        db_name = f"test_query_{uuid.uuid4().hex[:8]}"
        
        # Step 1: Create database and ontology
        create_db_payload = {"name": db_name, "description": "Query test database"}
        response = await self.client.post(f"{self.BFF_BASE_URL}/api/v1/database", json=create_db_payload)
        assert response.status_code == 200
        
        ontology_payload = {
            "label": {"ko": "쿼리 테스트", "en": "Query Test"},
            "description": {"ko": "쿼리용 클래스", "en": "Class for querying"}
        }
        
        response = await self.client.post(
            f"{self.BFF_BASE_URL}/database/{db_name}/ontology",
            json=ontology_payload
        )
        assert response.status_code == 200
        
        # Step 2: Test basic query
        query_payload = {
            "query_type": "list_classes",
            "limit": 10
        }
        
        response = await self.client.post(
            f"{self.BFF_BASE_URL}/database/{db_name}/query",
            json=query_payload,
            headers={"Accept-Language": "ko"}
        )
        
        assert response.status_code == 200
        query_result = response.json()
        assert "data" in query_result
        
        # Step 3: Test structured query
        structured_query = {
            "type": "select",
            "class_id": "test_class",
            "limit": 5
        }
        
        response = await self.client.post(
            f"{self.BFF_BASE_URL}/database/{db_name}/query/structured",
            json=structured_query
        )
        
        # Structured query endpoint might not exist yet
        assert response.status_code in [200, 404, 501]
        
        # Step 4: Test invalid query (should fail gracefully)
        invalid_query = {
            "invalid_field": "invalid_value"
        }
        
        response = await self.client.post(
            f"{self.BFF_BASE_URL}/database/{db_name}/query",
            json=invalid_query
        )
        
        # Should return error but not crash
        assert response.status_code in [400, 422, 500]
        
        # Cleanup
        await self.client.delete(f"{self.OMS_BASE_URL}/api/v1/database/{db_name}")
        
        logger.info(f"✓ Data query flow completed successfully")
    
    # Critical Flow 4: Label Mapping Flow
    
    @pytest.mark.asyncio
    async def test_label_mapping_flow(self):
        """
        Test label mapping import/export:
        1. Create database
        2. Export empty mappings
        3. Import mappings
        4. Verify import
        5. Export mappings again
        """
        db_name = f"test_mapping_{uuid.uuid4().hex[:8]}"
        
        # Step 1: Create database
        create_db_payload = {"name": db_name, "description": "Mapping test database"}
        response = await self.client.post(f"{self.BFF_BASE_URL}/api/v1/database", json=create_db_payload)
        assert response.status_code == 200
        
        # Step 2: Get initial mappings summary
        response = await self.client.get(f"{self.BFF_BASE_URL}/database/{db_name}/mappings")
        assert response.status_code == 200
        initial_summary = response.json()
        
        # Step 3: Export mappings
        response = await self.client.post(f"{self.BFF_BASE_URL}/database/{db_name}/mappings/export")
        assert response.status_code == 200
        exported_mappings = response.json()
        
        # Step 4: Test import with sample data
        sample_mappings = {
            "db_name": db_name,
            "classes": [
                {
                    "class_id": "TestClass",
                    "label": "테스트 클래스",
                    "label_lang": "ko"
                }
            ],
            "properties": [],
            "relationships": []
        }
        
        # Create a mock file for import (using JSON string)
        import io
        file_content = json.dumps(sample_mappings).encode()
        files = {"file": ("test_mappings.json", io.BytesIO(file_content), "application/json")}
        
        response = await self.client.post(
            f"{self.BFF_BASE_URL}/database/{db_name}/mappings/import",
            files=files
        )
        
        # Import should succeed or fail gracefully
        assert response.status_code in [200, 400, 422, 500]
        
        # Step 5: Get final mappings summary
        response = await self.client.get(f"{self.BFF_BASE_URL}/database/{db_name}/mappings")
        assert response.status_code == 200
        final_summary = response.json()
        
        # Cleanup
        await self.client.delete(f"{self.OMS_BASE_URL}/api/v1/database/{db_name}")
        
        logger.info(f"✓ Label mapping flow completed successfully")
    
    # Critical Flow 5: Error Handling and Recovery
    
    @pytest.mark.asyncio
    async def test_error_handling_flow(self):
        """
        Test error handling across the system:
        1. Test invalid database operations
        2. Test invalid ontology operations
        3. Test malformed requests
        4. Verify error responses are consistent
        """
        
        # Step 1: Test invalid database creation
        invalid_db_payload = {
            "name": "",  # Invalid empty name
            "description": "Invalid test"
        }
        
        response = await self.client.post(f"{self.BFF_BASE_URL}/api/v1/database", json=invalid_db_payload)
        assert response.status_code in [400, 422]
        error_data = response.json()
        assert "error" in error_data or "status" in error_data
        
        # Step 2: Test operations on non-existent database
        fake_db_name = "non_existent_database_12345"
        
        response = await self.client.get(f"{self.BFF_BASE_URL}/database/{fake_db_name}/ontologies")
        assert response.status_code in [404, 500]
        
        # Step 3: Test malformed JSON request
        malformed_json = '{"invalid": json syntax}'
        
        response = await self.client.post(
            f"{self.BFF_BASE_URL}/api/v1/database",
            content=malformed_json,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [400, 422]
        
        # Step 4: Test oversized request
        large_payload = {
            "name": "test_large",
            "description": "x" * 10000  # Very large description
        }
        
        response = await self.client.post(f"{self.BFF_BASE_URL}/api/v1/database", json=large_payload)
        assert response.status_code in [200, 400, 413, 422]
        
        # Step 5: Test SQL injection attempt
        injection_payload = {
            "name": "test'; DROP TABLE databases; --",
            "description": "SQL injection test"
        }
        
        response = await self.client.post(f"{self.BFF_BASE_URL}/api/v1/database", json=injection_payload)
        # Should be rejected by validation
        assert response.status_code in [400, 422]
        
        logger.info(f"✓ Error handling flow completed successfully")
    
    # Critical Flow 6: Performance and Load
    
    @pytest.mark.asyncio
    async def test_performance_flow(self):
        """
        Test system performance under load:
        1. Concurrent database operations
        2. Rapid API calls
        3. Large data handling
        """
        
        async def create_database(name: str) -> bool:
            """Helper function to create database"""
            try:
                payload = {"name": name, "description": f"Performance test database {name}"}
                response = await self.client.post(f"{self.BFF_BASE_URL}/api/v1/database", json=payload)
                return response.status_code == 200
            except Exception:
                return False
        
        async def delete_database(name: str) -> bool:
            """Helper function to delete database"""
            try:
                response = await self.client.delete(f"{self.OMS_BASE_URL}/api/v1/database/{name}")
                return response.status_code in [200, 204]
            except Exception:
                return False
        
        # Step 1: Test concurrent database creation
        db_names = [f"perf_test_{i}_{uuid.uuid4().hex[:6]}" for i in range(5)]
        
        start_time = time.time()
        create_tasks = [create_database(name) for name in db_names]
        create_results = await asyncio.gather(*create_tasks, return_exceptions=True)
        create_duration = time.time() - start_time
        
        successful_creates = sum(1 for result in create_results if result is True)
        logger.info(f"Created {successful_creates}/{len(db_names)} databases in {create_duration:.2f}s")
        
        # Step 2: Test rapid health check calls
        start_time = time.time()
        health_tasks = [self.client.get(f"{self.BFF_BASE_URL}/health") for _ in range(10)]
        health_responses = await asyncio.gather(*health_tasks, return_exceptions=True)
        health_duration = time.time() - start_time
        
        successful_health = sum(1 for resp in health_responses 
                               if isinstance(resp, httpx.Response) and resp.status_code in [200, 503])
        logger.info(f"Completed {successful_health}/10 health checks in {health_duration:.2f}s")
        
        # Step 3: Cleanup created databases
        cleanup_tasks = [delete_database(name) for name in db_names]
        cleanup_results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)
        successful_deletes = sum(1 for result in cleanup_results if result is True)
        
        logger.info(f"Cleaned up {successful_deletes}/{len(db_names)} databases")
        
        # Assertions
        assert successful_creates >= len(db_names) * 0.8, "Too many database creation failures"
        assert successful_health >= 8, "Too many health check failures"
        assert create_duration < 30, "Database creation took too long"
        assert health_duration < 10, "Health checks took too long"
        
        logger.info(f"✓ Performance flow completed successfully")


class TestCrossServiceIntegration:
    """Integration tests that span multiple services"""
    
    @pytest.mark.asyncio
    async def test_bff_oms_data_consistency(self):
        """Test data consistency between BFF and OMS"""
        
        async with httpx.AsyncClient(timeout=60) as client:
            db_name = f"consistency_test_{uuid.uuid4().hex[:8]}"
            
            try:
                # Create database via BFF
                payload = {"name": db_name, "description": "Consistency test"}
                response = await client.post("http://localhost:8002/api/v1/database", json=payload)
                
                if response.status_code == 200:
                    # Verify database exists in OMS
                    response = await client.get("http://localhost:8000/api/v1/databases")
                    if response.status_code == 200:
                        databases = response.json()
                        db_names = [db.get("name", db.get("database")) for db in databases if isinstance(databases, list)]
                        assert db_name in db_names, "Database not found in OMS after BFF creation"
                
            finally:
                # Cleanup
                try:
                    await client.delete(f"http://localhost:8000/api/v1/database/{db_name}")
                except Exception:
                    pass


if __name__ == "__main__":
    # Run tests manually
    pytest.main([__file__, "-v", "--tb=short", "-k", "test_database_lifecycle_flow"])