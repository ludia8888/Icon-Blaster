#!/usr/bin/env python
"""
Full Stack Integration Test Suite
Tests all TerminusDB extension features with actual services
"""
import asyncio
import httpx
import json
import time
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Service configuration
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
TERMINUS_URL = os.getenv("TERMINUS_URL", "http://localhost:6363")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
JAEGER_URL = os.getenv("JAEGER_URL", "http://localhost:16686")

print("🚀 OMS Full Stack Integration Tests")
print("=" * 80)
print(f"📡 API URL: {BASE_URL}")
print(f"🗄️  TerminusDB: {TERMINUS_URL}")
print(f"💾 Redis: {REDIS_URL}")
print(f"🔍 Jaeger: {JAEGER_URL}")
print("=" * 80)

class FullStackTester:
    """Full stack test orchestrator"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self.results = []
        self.start_time = time.time()
    
    async def close(self):
        await self.client.aclose()
    
    async def test_service_health(self, name: str, url: str, expected_status: int = 200) -> bool:
        """Test if a service is healthy"""
        try:
            response = await self.client.get(url)
            success = response.status_code == expected_status
            self.results.append({
                "test": f"{name} Health",
                "success": success,
                "details": f"Status: {response.status_code}"
            })
            return success
        except Exception as e:
            self.results.append({
                "test": f"{name} Health",
                "success": False,
                "details": f"Error: {str(e)}"
            })
            return False
    
    async def wait_for_services(self, max_retries: int = 30):
        """Wait for all services to be ready"""
        print("\n⏳ Waiting for services to be ready...")
        
        services = [
            ("OMS API", f"{BASE_URL}/health"),
            ("TerminusDB", f"{TERMINUS_URL}/_system"),
            ("Jaeger", f"{JAEGER_URL}/api/services"),
        ]
        
        for retry in range(max_retries):
            all_ready = True
            for name, url in services:
                try:
                    response = await self.client.get(url, follow_redirects=True)
                    if response.status_code not in [200, 302, 303]:
                        all_ready = False
                        print(f"  ⏸️  {name} not ready (status: {response.status_code})")
                except Exception:
                    all_ready = False
                    print(f"  ⏸️  {name} not reachable")
            
            if all_ready:
                print("  ✅ All services are ready!")
                return True
            
            print(f"  🔄 Retry {retry + 1}/{max_retries}...")
            await asyncio.sleep(2)
        
        return False

    async def test_delta_encoding(self):
        """Test delta encoding with TerminusDB"""
        print("\n🧪 Testing Delta Encoding...")
        
        try:
            # Create test documents
            doc1 = {
                "id": "test_doc_1",
                "version": 1,
                "data": {"name": "Test", "value": 100},
                "timestamp": datetime.now().isoformat()
            }
            
            doc2 = {
                "id": "test_doc_1",
                "version": 2,
                "data": {"name": "Test Updated", "value": 200, "new_field": "added"},
                "timestamp": (datetime.now() + timedelta(seconds=1)).isoformat()
            }
            
            # Test delta encoding endpoint
            response = await self.client.post(
                f"{BASE_URL}/api/v1/delta/encode",
                json={"old": doc1, "new": doc2}
            )
            
            if response.status_code == 200:
                result = response.json()
                self.results.append({
                    "test": "Delta Encoding",
                    "success": True,
                    "details": f"Delta size: {result.get('size', 'N/A')} bytes, Compression: {result.get('compression_ratio', 'N/A')}"
                })
            else:
                self.results.append({
                    "test": "Delta Encoding",
                    "success": False,
                    "details": f"Status: {response.status_code}"
                })
                
        except Exception as e:
            self.results.append({
                "test": "Delta Encoding",
                "success": False,
                "details": f"Error: {str(e)}"
            })

    async def test_vector_embeddings(self):
        """Test vector embedding service"""
        print("\n🧪 Testing Vector Embeddings...")
        
        try:
            # Test embedding generation
            texts = [
                "Machine learning is fascinating",
                "Deep learning models are powerful",
                "Natural language processing helps computers understand text"
            ]
            
            response = await self.client.post(
                f"{BASE_URL}/api/v1/embeddings/generate",
                json={"texts": texts, "provider": "local"}
            )
            
            if response.status_code == 200:
                result = response.json()
                embeddings = result.get("embeddings", [])
                
                # Test similarity search
                search_response = await self.client.post(
                    f"{BASE_URL}/api/v1/embeddings/search",
                    json={
                        "query": "machine learning algorithms",
                        "embeddings": embeddings,
                        "top_k": 2
                    }
                )
                
                if search_response.status_code == 200:
                    search_result = search_response.json()
                    self.results.append({
                        "test": "Vector Embeddings",
                        "success": True,
                        "details": f"Generated {len(embeddings)} embeddings, Top match: {search_result.get('results', [{}])[0].get('score', 'N/A')}"
                    })
                else:
                    self.results.append({
                        "test": "Vector Embeddings",
                        "success": False,
                        "details": f"Search failed: {search_response.status_code}"
                    })
            else:
                self.results.append({
                    "test": "Vector Embeddings",
                    "success": False,
                    "details": f"Generation failed: {response.status_code}"
                })
                
        except Exception as e:
            self.results.append({
                "test": "Vector Embeddings",
                "success": False,
                "details": f"Error: {str(e)}"
            })

    async def test_time_travel(self):
        """Test time travel queries"""
        print("\n🧪 Testing Time Travel Queries...")
        
        try:
            # Create versioned document
            resource_id = "time_travel_test"
            
            # Create multiple versions
            for i in range(3):
                response = await self.client.post(
                    f"{BASE_URL}/api/v1/time-travel/resource",
                    json={
                        "resource_id": resource_id,
                        "data": {"version": i + 1, "content": f"Version {i + 1}"},
                        "timestamp": (datetime.now() + timedelta(seconds=i)).isoformat()
                    }
                )
            
            # Test AS OF query
            as_of_time = (datetime.now() + timedelta(seconds=1)).isoformat()
            as_of_response = await self.client.get(
                f"{BASE_URL}/api/v1/time-travel/as-of/{resource_id}",
                params={"timestamp": as_of_time}
            )
            
            if as_of_response.status_code == 200:
                as_of_result = as_of_response.json()
                
                # Test BETWEEN query
                between_response = await self.client.get(
                    f"{BASE_URL}/api/v1/time-travel/between/{resource_id}",
                    params={
                        "start": datetime.now().isoformat(),
                        "end": (datetime.now() + timedelta(seconds=3)).isoformat()
                    }
                )
                
                if between_response.status_code == 200:
                    between_result = between_response.json()
                    self.results.append({
                        "test": "Time Travel Queries",
                        "success": True,
                        "details": f"AS OF returned version {as_of_result.get('data', {}).get('version', 'N/A')}, BETWEEN found {len(between_result.get('versions', []))} versions"
                    })
                else:
                    self.results.append({
                        "test": "Time Travel Queries",
                        "success": False,
                        "details": f"BETWEEN query failed: {between_response.status_code}"
                    })
            else:
                self.results.append({
                    "test": "Time Travel Queries",
                    "success": False,
                    "details": f"AS OF query failed: {as_of_response.status_code}"
                })
                
        except Exception as e:
            self.results.append({
                "test": "Time Travel Queries",
                "success": False,
                "details": f"Error: {str(e)}"
            })

    async def test_smart_cache(self):
        """Test multi-tier caching"""
        print("\n🧪 Testing Smart Cache...")
        
        try:
            # Test cache set
            key = f"test_key_{int(time.time())}"
            value = {"data": "test_value", "timestamp": datetime.now().isoformat()}
            
            set_response = await self.client.post(
                f"{BASE_URL}/api/v1/cache/set",
                json={"key": key, "value": value, "ttl": 300}
            )
            
            if set_response.status_code == 200:
                # Test cache get
                get_response = await self.client.get(
                    f"{BASE_URL}/api/v1/cache/get/{key}"
                )
                
                if get_response.status_code == 200:
                    cached_value = get_response.json()
                    
                    # Test cache stats
                    stats_response = await self.client.get(
                        f"{BASE_URL}/api/v1/cache/stats"
                    )
                    
                    if stats_response.status_code == 200:
                        stats = stats_response.json()
                        self.results.append({
                            "test": "Smart Cache",
                            "success": True,
                            "details": f"Cache working, Hit rate: {stats.get('hit_rate', 'N/A')}, Total ops: {stats.get('total_operations', 'N/A')}"
                        })
                    else:
                        self.results.append({
                            "test": "Smart Cache",
                            "success": True,
                            "details": "Cache working, stats unavailable"
                        })
                else:
                    self.results.append({
                        "test": "Smart Cache",
                        "success": False,
                        "details": f"Cache get failed: {get_response.status_code}"
                    })
            else:
                self.results.append({
                    "test": "Smart Cache",
                    "success": False,
                    "details": f"Cache set failed: {set_response.status_code}"
                })
                
        except Exception as e:
            self.results.append({
                "test": "Smart Cache",
                "success": False,
                "details": f"Error: {str(e)}"
            })

    async def test_graph_analysis(self):
        """Test GraphQL deep linking"""
        print("\n🧪 Testing Graph Analysis...")
        
        try:
            # GraphQL query for deep linking
            query = """
            query TestDeepLinking {
                user(id: "1") {
                    id
                    name
                    posts {
                        id
                        title
                        comments {
                            id
                            content
                            author {
                                id
                                name
                            }
                        }
                    }
                }
            }
            """
            
            response = await self.client.post(
                f"{BASE_URL}/graphql",
                json={"query": query}
            )
            
            if response.status_code == 200:
                result = response.json()
                if "errors" not in result:
                    self.results.append({
                        "test": "Graph Analysis (Deep Linking)",
                        "success": True,
                        "details": "GraphQL deep linking working"
                    })
                else:
                    self.results.append({
                        "test": "Graph Analysis (Deep Linking)",
                        "success": False,
                        "details": f"GraphQL errors: {result['errors']}"
                    })
            else:
                self.results.append({
                    "test": "Graph Analysis (Deep Linking)",
                    "success": False,
                    "details": f"GraphQL request failed: {response.status_code}"
                })
                
        except Exception as e:
            self.results.append({
                "test": "Graph Analysis (Deep Linking)",
                "success": False,
                "details": f"Error: {str(e)}"
            })

    async def test_unfoldable_documents(self):
        """Test unfoldable document processing"""
        print("\n🧪 Testing Unfoldable Documents...")
        
        try:
            # Create document with unfoldable sections
            document = {
                "id": "unfoldable_test",
                "title": "Test Document",
                "@unfoldable": {
                    "large_data": {
                        "summary": "Large dataset with 1000 items",
                        "content": list(range(1000))
                    },
                    "complex_object": {
                        "summary": "Complex nested structure",
                        "content": {
                            "nested": {"deep": {"data": "value" * 100}}
                        }
                    }
                }
            }
            
            # Test folding
            fold_response = await self.client.post(
                f"{BASE_URL}/api/v1/documents/fold",
                json={"document": document, "level": "collapsed"}
            )
            
            if fold_response.status_code == 200:
                folded = fold_response.json()
                
                # Test unfolding specific path
                unfold_response = await self.client.post(
                    f"{BASE_URL}/api/v1/documents/unfold",
                    json={
                        "document": folded,
                        "path": "@unfoldable.large_data"
                    }
                )
                
                if unfold_response.status_code == 200:
                    self.results.append({
                        "test": "Unfoldable Documents",
                        "success": True,
                        "details": "Document folding/unfolding working"
                    })
                else:
                    self.results.append({
                        "test": "Unfoldable Documents",
                        "success": False,
                        "details": f"Unfold failed: {unfold_response.status_code}"
                    })
            else:
                self.results.append({
                    "test": "Unfoldable Documents",
                    "success": False,
                    "details": f"Fold failed: {fold_response.status_code}"
                })
                
        except Exception as e:
            self.results.append({
                "test": "Unfoldable Documents",
                "success": False,
                "details": f"Error: {str(e)}"
            })

    async def test_metadata_frames(self):
        """Test metadata frame processing"""
        print("\n🧪 Testing Metadata Frames...")
        
        try:
            # Markdown with metadata frames
            markdown_content = """# API Documentation

```@metadata:api yaml
endpoint: /api/v1/users
method: GET
auth: required
```

This endpoint returns user information.

```@metadata:schema json
{
  "User": {
    "type": "object",
    "properties": {
      "id": {"type": "string"},
      "name": {"type": "string"},
      "email": {"type": "string"}
    }
  }
}
```

Example usage provided below.
"""
            
            response = await self.client.post(
                f"{BASE_URL}/api/v1/metadata/parse",
                json={"content": markdown_content}
            )
            
            if response.status_code == 200:
                result = response.json()
                frames = result.get("frames", [])
                
                if len(frames) >= 2:
                    self.results.append({
                        "test": "Metadata Frames",
                        "success": True,
                        "details": f"Parsed {len(frames)} metadata frames"
                    })
                else:
                    self.results.append({
                        "test": "Metadata Frames",
                        "success": False,
                        "details": f"Expected 2 frames, got {len(frames)}"
                    })
            else:
                self.results.append({
                    "test": "Metadata Frames",
                    "success": False,
                    "details": f"Parse failed: {response.status_code}"
                })
                
        except Exception as e:
            self.results.append({
                "test": "Metadata Frames",
                "success": False,
                "details": f"Error: {str(e)}"
            })

    async def test_jaeger_tracing(self):
        """Test distributed tracing integration"""
        print("\n🧪 Testing Jaeger Tracing...")
        
        try:
            # Make a traced request
            headers = {
                "X-Trace-ID": f"test-trace-{int(time.time())}",
                "X-Span-ID": "test-span-1"
            }
            
            response = await self.client.get(
                f"{BASE_URL}/api/v1/traced-endpoint",
                headers=headers
            )
            
            # Check if trace was recorded in Jaeger
            await asyncio.sleep(2)  # Give Jaeger time to process
            
            jaeger_response = await self.client.get(
                f"{JAEGER_URL}/api/traces",
                params={"service": "oms-monolith", "limit": 10}
            )
            
            if jaeger_response.status_code == 200:
                traces = jaeger_response.json().get("data", [])
                self.results.append({
                    "test": "Jaeger Tracing",
                    "success": True,
                    "details": f"Tracing active, found {len(traces)} recent traces"
                })
            else:
                self.results.append({
                    "test": "Jaeger Tracing",
                    "success": False,
                    "details": f"Jaeger query failed: {jaeger_response.status_code}"
                })
                
        except Exception as e:
            self.results.append({
                "test": "Jaeger Tracing",
                "success": False,
                "details": f"Error: {str(e)}"
            })

    async def test_audit_logging(self):
        """Test audit logging with PostgreSQL"""
        print("\n🧪 Testing Audit Logging...")
        
        try:
            # Create an auditable action
            audit_event = {
                "action": "test_action",
                "resource": "test_resource",
                "user_id": "test_user",
                "details": {"test": "data"},
                "timestamp": datetime.now().isoformat()
            }
            
            response = await self.client.post(
                f"{BASE_URL}/api/v1/audit/log",
                json=audit_event
            )
            
            if response.status_code == 200:
                # Query audit logs
                query_response = await self.client.get(
                    f"{BASE_URL}/api/v1/audit/logs",
                    params={"action": "test_action", "limit": 10}
                )
                
                if query_response.status_code == 200:
                    logs = query_response.json().get("logs", [])
                    self.results.append({
                        "test": "Audit Logging",
                        "success": True,
                        "details": f"Audit logging working, found {len(logs)} matching logs"
                    })
                else:
                    self.results.append({
                        "test": "Audit Logging",
                        "success": False,
                        "details": f"Audit query failed: {query_response.status_code}"
                    })
            else:
                self.results.append({
                    "test": "Audit Logging",
                    "success": False,
                    "details": f"Audit log creation failed: {response.status_code}"
                })
                
        except Exception as e:
            self.results.append({
                "test": "Audit Logging",
                "success": False,
                "details": f"Error: {str(e)}"
            })

    def print_report(self):
        """Print test results report"""
        print("\n" + "=" * 80)
        print("📊 FULL STACK TEST REPORT")
        print("=" * 80)
        print(f"Total Time: {time.time() - self.start_time:.2f} seconds\n")
        
        # Summary
        passed = sum(1 for r in self.results if r["success"])
        failed = sum(1 for r in self.results if not r["success"])
        total = len(self.results)
        
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"📈 Total: {total}")
        print(f"🎯 Success Rate: {(passed/total*100):.1f}%" if total > 0 else "N/A")
        
        # Detailed results
        print("\nDetailed Results:")
        print("-" * 80)
        for result in self.results:
            status = "✅" if result["success"] else "❌"
            print(f"{status} {result['test']:<30} {result['details']}")
        
        # Failed tests details
        if failed > 0:
            print("\n❌ Failed Tests Details:")
            for result in self.results:
                if not result["success"]:
                    print(f"  - {result['test']}: {result['details']}")

async def main():
    """Run full stack tests"""
    tester = FullStackTester()
    
    try:
        # Wait for services
        if not await tester.wait_for_services():
            print("\n❌ Services did not start in time. Exiting...")
            return 1
        
        # Run service health checks
        print("\n🏥 Checking Service Health...")
        await tester.test_service_health("OMS API", f"{BASE_URL}/health")
        await tester.test_service_health("TerminusDB", f"{TERMINUS_URL}/_system")
        await tester.test_service_health("Jaeger", f"{JAEGER_URL}/")
        
        # Run feature tests
        await tester.test_delta_encoding()
        await tester.test_vector_embeddings()
        await tester.test_time_travel()
        await tester.test_smart_cache()
        await tester.test_graph_analysis()
        await tester.test_unfoldable_documents()
        await tester.test_metadata_frames()
        await tester.test_jaeger_tracing()
        await tester.test_audit_logging()
        
        # Print report
        tester.print_report()
        
        # Return exit code
        failed = sum(1 for r in tester.results if not r["success"])
        return 0 if failed == 0 else 1
        
    finally:
        await tester.close()

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)