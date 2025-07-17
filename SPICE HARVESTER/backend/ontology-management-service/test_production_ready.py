#!/usr/bin/env python3
"""
Comprehensive Production Readiness Test Suite for BFF -> OMS -> TerminusDB
Tests all features, edge cases, and error handling
"""

import asyncio
import json
import httpx
import time
from typing import Dict, Any, List
from datetime import datetime

# Configuration
BFF_URL = "http://localhost:8002"
OMS_URL = "http://localhost:8000"
TEST_DB_PREFIX = f"test_prod_{int(time.time())}"

class ProductionReadinessTest:
    def __init__(self):
        self.bff_client = httpx.AsyncClient(base_url=BFF_URL, timeout=30.0)
        self.oms_client = httpx.AsyncClient(base_url=OMS_URL, timeout=30.0)
        self.test_results = []
        self.test_db_name = f"{TEST_DB_PREFIX}_db"
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.bff_client.aclose()
        await self.oms_client.aclose()
        
    def log_test(self, test_name: str, passed: bool, details: str = "", error: str = ""):
        """Log test results"""
        result = {
            "test": test_name,
            "passed": passed,
            "details": details,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"\n{status}: {test_name}")
        if details:
            print(f"  Details: {details}")
        if error:
            print(f"  Error: {error}")
            
    async def test_health_endpoints(self):
        """Test 1: Verify both services are healthy"""
        print("\n" + "="*60)
        print("TEST 1: Health Check Endpoints")
        print("="*60)
        
        # Test BFF health
        try:
            response = await self.bff_client.get("/health")
            bff_healthy = response.status_code == 200
            bff_data = response.json()
            self.log_test(
                "BFF Health Check",
                bff_healthy,
                f"Status: {bff_data.get('status', 'unknown')}"
            )
        except Exception as e:
            self.log_test("BFF Health Check", False, error=str(e))
            return False
            
        # Test OMS health
        try:
            response = await self.oms_client.get("/health")
            oms_healthy = response.status_code == 200
            oms_data = response.json()
            self.log_test(
                "OMS Health Check",
                oms_healthy,
                f"Status: {oms_data.get('status', 'unknown')}"
            )
        except Exception as e:
            self.log_test("OMS Health Check", False, error=str(e))
            return False
            
        return bff_healthy and oms_healthy
        
    async def test_database_creation(self):
        """Test 2: Create test database through BFF"""
        print("\n" + "="*60)
        print("TEST 2: Database Creation")
        print("="*60)
        
        # Test valid database creation
        try:
            response = await self.bff_client.post(
                "/api/v1/databases",
                json={
                    "name": self.test_db_name,
                    "description": "Production readiness test database"
                }
            )
            success = response.status_code == 200
            data = response.json()
            self.log_test(
                "Create Database",
                success,
                f"Database: {data.get('name', 'unknown')}"
            )
        except Exception as e:
            self.log_test("Create Database", False, error=str(e))
            return False
            
        # Test duplicate database creation (should fail)
        try:
            response = await self.bff_client.post(
                "/api/v1/databases",
                json={"name": self.test_db_name}
            )
            # Should fail with 409 or 400
            success = response.status_code in [400, 409]
            self.log_test(
                "Duplicate Database Prevention",
                success,
                f"Status: {response.status_code}"
            )
        except Exception as e:
            self.log_test("Duplicate Database Prevention", False, error=str(e))
            
        # Test invalid database name
        try:
            response = await self.bff_client.post(
                "/api/v1/databases",
                json={"name": "invalid-name-with-hyphens"}
            )
            success = response.status_code == 400
            self.log_test(
                "Invalid Database Name Validation",
                success,
                f"Status: {response.status_code}"
            )
        except Exception as e:
            self.log_test("Invalid Database Name Validation", False, error=str(e))
            
        return True
        
    async def test_ontology_operations(self):
        """Test 3: Create and manage ontology classes"""
        print("\n" + "="*60)
        print("TEST 3: Ontology Operations")
        print("="*60)
        
        # Create a complex ontology class
        person_class = {
            "@type": "Class",
            "@id": "Person",
            "@label": {
                "en": "Person",
                "es": "Persona",
                "fr": "Personne"
            },
            "@documentation": {
                "en": "Represents a person entity",
                "es": "Representa una entidad persona"
            },
            "properties": {
                "name": {
                    "@type": "xsd:string",
                    "@label": {"en": "Name", "es": "Nombre"},
                    "@documentation": {"en": "Person's full name"},
                    "@mandatory": True
                },
                "age": {
                    "@type": "xsd:integer",
                    "@label": {"en": "Age", "es": "Edad"},
                    "@minimum": 0,
                    "@maximum": 150
                },
                "email": {
                    "@type": "xsd:string",
                    "@label": {"en": "Email", "es": "Correo"},
                    "@format": "email",
                    "@unique": True
                },
                "skills": {
                    "@type": "Set",
                    "@class": "xsd:string",
                    "@label": {"en": "Skills", "es": "Habilidades"}
                }
            }
        }
        
        # Test creating ontology class
        try:
            response = await self.bff_client.post(
                f"/api/v1/databases/{self.test_db_name}/classes",
                json=person_class
            )
            success = response.status_code == 200
            data = response.json()
            self.log_test(
                "Create Ontology Class",
                success,
                f"Class: {data.get('@id', 'unknown')}"
            )
        except Exception as e:
            self.log_test("Create Ontology Class", False, error=str(e))
            return False
            
        # Test retrieving class with label mapping
        try:
            response = await self.bff_client.get(
                f"/api/v1/databases/{self.test_db_name}/classes/Person",
                params={"language": "es"}
            )
            success = response.status_code == 200
            data = response.json()
            spanish_label = data.get("@label", {}).get("es") == "Persona"
            self.log_test(
                "Retrieve Class with Spanish Labels",
                success and spanish_label,
                f"Label: {data.get('@label', {})}"
            )
        except Exception as e:
            self.log_test("Retrieve Class with Spanish Labels", False, error=str(e))
            
        # Test creating a relationship class
        works_for_class = {
            "@type": "Class",
            "@id": "WorksFor",
            "@label": {"en": "Works For"},
            "@inherits": ["Relationship"],
            "properties": {
                "from": {
                    "@type": "@id",
                    "@class": "Person",
                    "@label": {"en": "Employee"}
                },
                "to": {
                    "@type": "@id", 
                    "@class": "Company",
                    "@label": {"en": "Employer"}
                },
                "start_date": {
                    "@type": "xsd:date",
                    "@label": {"en": "Start Date"}
                }
            }
        }
        
        # First create Company class
        company_class = {
            "@type": "Class",
            "@id": "Company",
            "@label": {"en": "Company"},
            "properties": {
                "name": {
                    "@type": "xsd:string",
                    "@label": {"en": "Company Name"}
                }
            }
        }
        
        try:
            # Create Company class
            response = await self.bff_client.post(
                f"/api/v1/databases/{self.test_db_name}/classes",
                json=company_class
            )
            
            # Create WorksFor relationship
            response = await self.bff_client.post(
                f"/api/v1/databases/{self.test_db_name}/classes",
                json=works_for_class
            )
            success = response.status_code == 200
            self.log_test(
                "Create Relationship Class",
                success,
                "WorksFor relationship created"
            )
        except Exception as e:
            self.log_test("Create Relationship Class", False, error=str(e))
            
        return True
        
    async def test_error_handling(self):
        """Test 4: Comprehensive error handling"""
        print("\n" + "="*60)
        print("TEST 4: Error Handling")
        print("="*60)
        
        # Test missing required fields
        try:
            response = await self.bff_client.post(
                f"/api/v1/databases/{self.test_db_name}/classes",
                json={"@type": "Class"}  # Missing @id
            )
            success = response.status_code == 400
            self.log_test(
                "Missing Required Field Validation",
                success,
                f"Status: {response.status_code}"
            )
        except Exception as e:
            self.log_test("Missing Required Field Validation", False, error=str(e))
            
        # Test invalid property type
        try:
            response = await self.bff_client.post(
                f"/api/v1/databases/{self.test_db_name}/classes",
                json={
                    "@type": "Class",
                    "@id": "InvalidClass",
                    "properties": {
                        "invalid_prop": {
                            "@type": "invalid:type"  # Invalid type
                        }
                    }
                }
            )
            success = response.status_code == 400
            self.log_test(
                "Invalid Property Type Validation",
                success,
                f"Status: {response.status_code}"
            )
        except Exception as e:
            self.log_test("Invalid Property Type Validation", False, error=str(e))
            
        # Test non-existent database
        try:
            response = await self.bff_client.get(
                "/api/v1/databases/non_existent_db/classes"
            )
            success = response.status_code == 404
            self.log_test(
                "Non-existent Database Handling",
                success,
                f"Status: {response.status_code}"
            )
        except Exception as e:
            self.log_test("Non-existent Database Handling", False, error=str(e))
            
        # Test malformed JSON
        try:
            response = await self.bff_client.post(
                f"/api/v1/databases/{self.test_db_name}/classes",
                content="{invalid json",
                headers={"Content-Type": "application/json"}
            )
            success = response.status_code == 400
            self.log_test(
                "Malformed JSON Handling",
                success,
                f"Status: {response.status_code}"
            )
        except Exception as e:
            self.log_test("Malformed JSON Handling", False, error=str(e))
            
        return True
        
    async def test_branching_versioning(self):
        """Test 5: Branch and version management"""
        print("\n" + "="*60)
        print("TEST 5: Branching and Versioning")
        print("="*60)
        
        # Create a new branch
        try:
            response = await self.bff_client.post(
                f"/api/v1/databases/{self.test_db_name}/branches",
                json={
                    "name": "feature_branch",
                    "description": "Test feature branch"
                }
            )
            success = response.status_code == 200
            data = response.json()
            self.log_test(
                "Create Branch",
                success,
                f"Branch: {data.get('name', 'unknown')}"
            )
        except Exception as e:
            self.log_test("Create Branch", False, error=str(e))
            return False
            
        # List branches
        try:
            response = await self.bff_client.get(
                f"/api/v1/databases/{self.test_db_name}/branches"
            )
            success = response.status_code == 200
            data = response.json()
            branches = data.get("branches", [])
            has_branches = len(branches) >= 2  # main + feature_branch
            self.log_test(
                "List Branches",
                success and has_branches,
                f"Branches: {[b.get('name') for b in branches]}"
            )
        except Exception as e:
            self.log_test("List Branches", False, error=str(e))
            
        # Get version history
        try:
            response = await self.bff_client.get(
                f"/api/v1/databases/{self.test_db_name}/versions"
            )
            success = response.status_code == 200
            data = response.json()
            versions = data.get("versions", [])
            self.log_test(
                "Get Version History",
                success,
                f"Versions: {len(versions)}"
            )
        except Exception as e:
            self.log_test("Get Version History", False, error=str(e))
            
        return True
        
    async def test_query_operations(self):
        """Test 6: Query operations and filtering"""
        print("\n" + "="*60)
        print("TEST 6: Query Operations")
        print("="*60)
        
        # Test listing all classes
        try:
            response = await self.bff_client.get(
                f"/api/v1/databases/{self.test_db_name}/classes"
            )
            success = response.status_code == 200
            data = response.json()
            classes = data.get("classes", [])
            self.log_test(
                "List All Classes",
                success,
                f"Classes found: {len(classes)}"
            )
        except Exception as e:
            self.log_test("List All Classes", False, error=str(e))
            
        # Test filtering with query parameters
        try:
            response = await self.bff_client.get(
                f"/api/v1/databases/{self.test_db_name}/classes",
                params={"type": "Class", "limit": 10}
            )
            success = response.status_code == 200
            self.log_test(
                "Query with Filters",
                success,
                "Filtered query successful"
            )
        except Exception as e:
            self.log_test("Query with Filters", False, error=str(e))
            
        return True
        
    async def test_performance_limits(self):
        """Test 7: Performance and rate limiting"""
        print("\n" + "="*60)
        print("TEST 7: Performance and Limits")
        print("="*60)
        
        # Test large payload
        large_class = {
            "@type": "Class",
            "@id": "LargeClass",
            "@label": {"en": "Large Class"},
            "properties": {}
        }
        
        # Add many properties
        for i in range(100):
            large_class["properties"][f"prop_{i}"] = {
                "@type": "xsd:string",
                "@label": {"en": f"Property {i}"}
            }
            
        try:
            start_time = time.time()
            response = await self.bff_client.post(
                f"/api/v1/databases/{self.test_db_name}/classes",
                json=large_class
            )
            elapsed = time.time() - start_time
            success = response.status_code == 200
            self.log_test(
                "Large Payload Handling",
                success,
                f"Elapsed: {elapsed:.2f}s, Properties: 100"
            )
        except Exception as e:
            self.log_test("Large Payload Handling", False, error=str(e))
            
        # Test concurrent requests
        async def make_request(index: int):
            try:
                response = await self.bff_client.get(
                    f"/api/v1/databases/{self.test_db_name}/classes/Person"
                )
                return response.status_code == 200
            except (httpx.HTTPError, asyncio.TimeoutError, ConnectionError):
                return False
                
        try:
            start_time = time.time()
            tasks = [make_request(i) for i in range(20)]
            results = await asyncio.gather(*tasks)
            elapsed = time.time() - start_time
            success_rate = sum(results) / len(results)
            
            self.log_test(
                "Concurrent Request Handling",
                success_rate >= 0.95,
                f"Success rate: {success_rate*100:.1f}%, Elapsed: {elapsed:.2f}s"
            )
        except Exception as e:
            self.log_test("Concurrent Request Handling", False, error=str(e))
            
        return True
        
    async def test_cleanup(self):
        """Test 8: Cleanup test database"""
        print("\n" + "="*60)
        print("TEST 8: Cleanup")
        print("="*60)
        
        try:
            response = await self.bff_client.delete(
                f"/api/v1/databases/{self.test_db_name}"
            )
            success = response.status_code in [200, 204]
            self.log_test(
                "Delete Test Database",
                success,
                f"Database {self.test_db_name} cleaned up"
            )
        except Exception as e:
            self.log_test("Delete Test Database", False, error=str(e))
            
        return True
        
    def generate_report(self):
        """Generate final test report"""
        print("\n" + "="*60)
        print("PRODUCTION READINESS TEST REPORT")
        print("="*60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["passed"])
        failed_tests = total_tests - passed_tests
        
        print(f"\nTotal Tests: {total_tests}")
        print(f"Passed: {passed_tests} ({passed_tests/total_tests*100:.1f}%)")
        print(f"Failed: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
        
        if failed_tests > 0:
            print("\n❌ FAILED TESTS:")
            for result in self.test_results:
                if not result["passed"]:
                    print(f"  - {result['test']}")
                    if result["error"]:
                        print(f"    Error: {result['error']}")
                        
        # Save detailed report
        report_file = f"production_test_report_{int(time.time())}.json"
        with open(report_file, "w") as f:
            json.dump({
                "summary": {
                    "total": total_tests,
                    "passed": passed_tests,
                    "failed": failed_tests,
                    "success_rate": f"{passed_tests/total_tests*100:.1f}%"
                },
                "details": self.test_results
            }, f, indent=2)
            
        print(f"\nDetailed report saved to: {report_file}")
        
        # Overall assessment
        if passed_tests == total_tests:
            print("\n✅ SYSTEM IS PRODUCTION READY!")
        elif passed_tests / total_tests >= 0.9:
            print("\n⚠️  SYSTEM IS MOSTLY READY - Minor issues to fix")
        else:
            print("\n❌ SYSTEM NOT PRODUCTION READY - Critical issues found")
            
        return passed_tests == total_tests
        
    async def run_all_tests(self):
        """Run complete test suite"""
        print("STARTING PRODUCTION READINESS TESTS")
        print("Time:", datetime.now().isoformat())
        
        # Run tests in sequence
        tests = [
            self.test_health_endpoints,
            self.test_database_creation,
            self.test_ontology_operations,
            self.test_error_handling,
            self.test_branching_versioning,
            self.test_query_operations,
            self.test_performance_limits,
            self.test_cleanup
        ]
        
        for test in tests:
            try:
                await test()
            except Exception as e:
                print(f"\n❌ CRITICAL ERROR in {test.__name__}: {e}")
                
        # Generate final report
        return self.generate_report()


async def main():
    """Main test runner"""
    async with ProductionReadinessTest() as tester:
        success = await tester.run_all_tests()
        return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)