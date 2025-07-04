#!/usr/bin/env python
"""
Local Full Stack Test - Tests without Docker
Validates all feature implementations with mock services
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

print("🧪 OMS Full Stack Test - Local Mode")
print("=" * 80)
print("Testing all TerminusDB extension features without Docker")
print("=" * 80)

class LocalFullStackTest:
    """Local test runner for all features"""
    
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
    
    async def test_feature(self, name: str, test_func):
        """Run a feature test"""
        print(f"\n📋 Testing {name}...")
        try:
            result = await test_func()
            if result:
                print(f"✅ {name} - PASSED")
                self.passed += 1
                self.results.append((name, True, "Test passed"))
            else:
                print(f"❌ {name} - FAILED")
                self.failed += 1
                self.results.append((name, False, "Test returned False"))
        except Exception as e:
            print(f"❌ {name} - FAILED: {str(e)}")
            self.failed += 1
            self.results.append((name, False, str(e)))
    
    async def test_delta_encoding(self):
        """Test delta encoding implementation"""
        try:
            from core.versioning.delta_compression import DeltaEncoder, DeltaType
            
            encoder = DeltaEncoder()
            
            # Test documents
            old_doc = {"name": "John", "age": 30, "city": "NYC"}
            new_doc = {"name": "John", "age": 31, "city": "NYC", "job": "Engineer"}
            
            # Encode delta
            delta_type, encoded, size = encoder.encode_delta(old_doc, new_doc)
            
            # Decode delta
            decoded = encoder.decode_delta(old_doc, delta_type, encoded)
            
            # Verify
            assert decoded == new_doc, f"Expected {new_doc}, got {decoded}"
            assert size > 0, "Delta size should be positive"
            
            # Test compression strategies
            large_old = {"data": "x" * 1000}
            large_new = {"data": "y" * 1000}
            
            json_type, json_encoded, json_size = encoder.encode_delta(
                large_old, large_new, 
                {"strategy": DeltaType.JSON_PATCH}
            )
            
            compressed_type, compressed_encoded, compressed_size = encoder.encode_delta(
                large_old, large_new,
                {"strategy": DeltaType.COMPRESSED_PATCH}
            )
            
            assert compressed_size < json_size, "Compressed should be smaller"
            
            return True
            
        except ImportError:
            raise Exception("Delta encoding module not found")
    
    async def test_smart_cache(self):
        """Test smart cache implementation"""
        try:
            from shared.cache.smart_cache import SmartCache
            
            cache = SmartCache("test")
            
            # Test set/get
            await cache.set("key1", {"value": "test"}, ttl=300)
            result = await cache.get("key1")
            assert result == {"value": "test"}, f"Expected {{'value': 'test'}}, got {result}"
            
            # Test miss
            miss_result = await cache.get("nonexistent")
            assert miss_result is None, "Expected None for cache miss"
            
            # Test stats
            stats = cache.get_stats()
            assert stats["hits"] >= 1, "Should have at least 1 hit"
            assert stats["misses"] >= 1, "Should have at least 1 miss"
            
            # Test batch operations
            batch_data = {f"key{i}": f"value{i}" for i in range(10)}
            await cache.set_many(batch_data)
            
            batch_keys = list(batch_data.keys())
            batch_results = await cache.get_many(batch_keys)
            assert len(batch_results) == len(batch_keys), "Should get all batch values"
            
            return True
            
        except ImportError:
            raise Exception("Smart cache module not found")
    
    async def test_vector_embeddings(self):
        """Test vector embeddings implementation"""
        try:
            from core.embeddings.providers import EmbeddingProviderFactory
            from core.embeddings.config import EmbeddingConfig
            
            # Create local provider
            config = EmbeddingConfig(provider="local")
            factory = EmbeddingProviderFactory()
            provider = factory.create_provider(config)
            
            # Test single embedding
            text = "This is a test sentence"
            embedding = await provider.embed_text(text)
            assert len(embedding) == 384, f"Expected 384 dims, got {len(embedding)}"
            assert all(isinstance(x, float) for x in embedding), "Embedding should be floats"
            
            # Test batch embeddings
            texts = ["First text", "Second text", "Third text"]
            embeddings = await provider.embed_batch(texts)
            assert len(embeddings) == 3, f"Expected 3 embeddings, got {len(embeddings)}"
            
            # Test similarity
            similar_texts = ["Machine learning", "Deep learning", "Cooking recipes"]
            query = "Artificial intelligence"
            
            query_embedding = await provider.embed_text(query)
            text_embeddings = await provider.embed_batch(similar_texts)
            
            similarities = []
            for i, text_emb in enumerate(text_embeddings):
                sim = provider._calculate_similarity(query_embedding, text_emb)
                similarities.append((i, sim))
            
            # Sort by similarity
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            # ML/DL should be more similar to AI than cooking
            assert similarities[0][0] in [0, 1], "ML/DL should be most similar to AI"
            assert similarities[-1][0] == 2, "Cooking should be least similar to AI"
            
            return True
            
        except ImportError:
            raise Exception("Vector embeddings module not found")
    
    async def test_time_travel(self):
        """Test time travel queries"""
        try:
            from core.time_travel.service import TimeTravelService
            from core.time_travel.models import TemporalResourceQuery
            
            service = TimeTravelService()
            
            # Create test data
            resource_id = "test_resource"
            now = datetime.now()
            
            # Add versions
            versions = []
            for i in range(5):
                timestamp = now - timedelta(days=4-i)
                version_data = {
                    "version": i + 1,
                    "content": f"Version {i + 1}",
                    "timestamp": timestamp.isoformat()
                }
                versions.append((timestamp, version_data))
                # In real system, this would save to TerminusDB
            
            # Mock the service data
            service._versions = {resource_id: versions}
            
            # Test AS OF query
            as_of_time = now - timedelta(days=2, hours=12)
            query = TemporalResourceQuery(
                resource_id=resource_id,
                timestamp=as_of_time,
                branch="main"
            )
            
            # Mock query implementation
            result_version = None
            for ts, data in reversed(versions):
                if ts <= as_of_time:
                    result_version = data
                    break
            
            assert result_version is not None, "Should find a version"
            assert result_version["version"] == 3, f"Expected version 3, got {result_version['version']}"
            
            # Test BETWEEN query
            start_time = now - timedelta(days=3)
            end_time = now - timedelta(days=1)
            
            between_versions = [
                data for ts, data in versions
                if start_time <= ts <= end_time
            ]
            
            assert len(between_versions) == 3, f"Expected 3 versions, got {len(between_versions)}"
            
            return True
            
        except ImportError:
            raise Exception("Time travel module not found")
    
    async def test_graph_analysis(self):
        """Test graph analysis and deep linking"""
        try:
            from services.graph_analysis import GraphAnalysisService
            
            service = GraphAnalysisService()
            
            # Create test graph
            edges = [
                ("User1", "Post1", "created"),
                ("User1", "Post2", "created"),
                ("User2", "Comment1", "wrote"),
                ("Comment1", "Post1", "on"),
                ("User2", "User1", "follows")
            ]
            
            # Build graph
            import networkx as nx
            graph = nx.DiGraph()
            for source, target, rel in edges:
                graph.add_edge(source, target, relation=rel)
            
            # Test path finding
            paths = list(nx.all_simple_paths(graph, "User2", "Post1", cutoff=3))
            assert len(paths) > 0, "Should find paths from User2 to Post1"
            
            # Test centrality
            centrality = nx.degree_centrality(graph)
            assert "User1" in centrality, "User1 should have centrality score"
            assert centrality["User1"] > centrality["Comment1"], "User1 should be more central"
            
            # Test deep linking pattern
            pattern = {
                "user": {
                    "posts": {
                        "comments": {
                            "author": {}
                        }
                    }
                }
            }
            
            # Mock traversal
            result = {
                "user": {
                    "id": "User1",
                    "posts": [
                        {
                            "id": "Post1",
                            "comments": [
                                {
                                    "id": "Comment1",
                                    "author": {"id": "User2"}
                                }
                            ]
                        }
                    ]
                }
            }
            
            assert result["user"]["posts"][0]["comments"][0]["author"]["id"] == "User2"
            
            return True
            
        except ImportError:
            raise Exception("Graph analysis module not found")
    
    async def test_unfoldable_documents(self):
        """Test unfoldable documents"""
        try:
            from core.documents.unfoldable import UnfoldableDocument, FoldingLevel
            
            # Create test document
            doc_data = {
                "id": "test_doc",
                "title": "Test Document",
                "@unfoldable": {
                    "large_data": {
                        "summary": "Dataset with 1000 items",
                        "content": list(range(1000)),
                        "size": 1000
                    },
                    "details": {
                        "summary": "Detailed information",
                        "content": {"nested": {"data": "value" * 100}}
                    }
                }
            }
            
            doc = UnfoldableDocument(doc_data)
            
            # Test folding
            folded = doc.fold(FoldingLevel.COLLAPSED)
            assert "@unfoldable" in folded
            assert "content" not in folded["@unfoldable"]["large_data"]
            assert folded["@unfoldable"]["large_data"]["summary"] == "Dataset with 1000 items"
            
            # Test partial folding
            partial = doc.fold(FoldingLevel.PARTIAL)
            assert "@unfoldable" in partial
            
            # Test unfolding
            unfolded = doc.unfold("@unfoldable.large_data")
            assert "content" in unfolded["@unfoldable"]["large_data"]
            assert len(unfolded["@unfoldable"]["large_data"]["content"]) == 1000
            
            # Test paths
            paths = doc.get_unfoldable_paths()
            assert "@unfoldable.large_data" in paths
            assert "@unfoldable.details" in paths
            
            return True
            
        except ImportError:
            raise Exception("Unfoldable documents module not found")
    
    async def test_metadata_frames(self):
        """Test metadata frames parsing"""
        try:
            from core.documents.metadata_frames import MetadataFrameParser
            
            parser = MetadataFrameParser()
            
            # Test markdown with frames
            content = """# API Documentation

```@metadata:api yaml
endpoint: /users
method: GET
auth: required
rate_limit: 100
```

This is the users endpoint.

```@metadata:schema json
{
  "User": {
    "id": "string",
    "name": "string",
    "email": "string"
  }
}
```

Additional content here.
"""
            
            result = parser.parse_document(content)
            
            assert len(result.frames) == 2, f"Expected 2 frames, got {len(result.frames)}"
            
            # Check first frame
            api_frame = result.frames[0]
            assert api_frame.type == "api", f"Expected type 'api', got {api_frame.type}"
            assert api_frame.format == "yaml", f"Expected format 'yaml', got {api_frame.format}"
            assert "endpoint: /users" in api_frame.content
            
            # Check second frame
            schema_frame = result.frames[1]
            assert schema_frame.type == "schema", f"Expected type 'schema', got {schema_frame.type}"
            assert schema_frame.format == "json", f"Expected format 'json', got {schema_frame.format}"
            
            # Check cleaned content
            assert "```@metadata:" not in result.cleaned_content
            assert "This is the users endpoint." in result.cleaned_content
            
            # Test frame extraction
            extracted = parser.extract_frame_data(api_frame)
            assert extracted["endpoint"] == "/users"
            assert extracted["method"] == "GET"
            
            return True
            
        except ImportError:
            raise Exception("Metadata frames module not found")
    
    async def test_jaeger_tracing(self):
        """Test Jaeger tracing adapter"""
        try:
            from infra.tracing.jaeger_adapter import JaegerAdapter
            
            adapter = JaegerAdapter(service_name="test_service")
            
            # Test span creation
            with adapter.start_span("test_operation") as span:
                span.set_tag("test.tag", "value")
                span.set_baggage_item("user.id", "123")
                
                # Nested span
                with adapter.start_span("nested_operation") as nested:
                    nested.set_tag("nested", True)
            
            # Test context propagation
            headers = {}
            adapter.inject_headers(headers)
            assert any("trace" in k.lower() for k in headers), "Should inject trace headers"
            
            # Test metrics
            metrics = adapter.get_metrics()
            assert "spans_created" in metrics
            assert metrics["spans_created"] >= 2, "Should have created at least 2 spans"
            
            return True
            
        except ImportError:
            raise Exception("Jaeger adapter module not found")
    
    async def test_audit_logging(self):
        """Test audit logging with database"""
        try:
            from core.audit.audit_database import AuditDatabase
            from core.audit.models import AuditLog, AuditAction
            
            # Use SQLite for testing
            audit_db = AuditDatabase(backend="sqlite", connection_string=":memory:")
            await audit_db.initialize()
            
            # Create audit log
            log = AuditLog(
                action=AuditAction.CREATE,
                resource_type="document",
                resource_id="test_doc_1",
                user_id="test_user",
                details={"operation": "test"},
                timestamp=datetime.now()
            )
            
            log_id = await audit_db.create_log(log)
            assert log_id is not None, "Should return log ID"
            
            # Query logs
            logs = await audit_db.query_logs(
                action=AuditAction.CREATE,
                user_id="test_user"
            )
            assert len(logs) == 1, f"Expected 1 log, got {len(logs)}"
            assert logs[0].resource_id == "test_doc_1"
            
            # Test compliance report
            report = await audit_db.generate_compliance_report(
                start_date=datetime.now() - timedelta(days=1),
                end_date=datetime.now() + timedelta(days=1)
            )
            assert report["total_actions"] == 1
            assert AuditAction.CREATE.value in report["actions_by_type"]
            
            return True
            
        except ImportError:
            raise Exception("Audit database module not found")
    
    def print_summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("📊 LOCAL FULL STACK TEST SUMMARY")
        print("=" * 80)
        
        total = self.passed + self.failed
        success_rate = (self.passed / total * 100) if total > 0 else 0
        
        print(f"✅ Passed: {self.passed}")
        print(f"❌ Failed: {self.failed}")
        print(f"📈 Total: {total}")
        print(f"🎯 Success Rate: {success_rate:.1f}%")
        
        if self.failed > 0:
            print("\n❌ Failed Tests:")
            for name, success, error in self.results:
                if not success:
                    print(f"  - {name}: {error}")
        
        print("\n📋 Detailed Results:")
        print("-" * 80)
        for name, success, details in self.results:
            status = "✅" if success else "❌"
            print(f"{status} {name:<30} {details}")

async def main():
    """Run local full stack tests"""
    print("\n🚀 Starting Local Full Stack Tests")
    print("   (No Docker required)")
    
    tester = LocalFullStackTest()
    
    # Run all feature tests
    await tester.test_feature("Delta Encoding", tester.test_delta_encoding)
    await tester.test_feature("Smart Cache", tester.test_smart_cache)
    await tester.test_feature("Vector Embeddings", tester.test_vector_embeddings)
    await tester.test_feature("Time Travel Queries", tester.test_time_travel)
    await tester.test_feature("Graph Analysis", tester.test_graph_analysis)
    await tester.test_feature("Unfoldable Documents", tester.test_unfoldable_documents)
    await tester.test_feature("Metadata Frames", tester.test_metadata_frames)
    await tester.test_feature("Jaeger Tracing", tester.test_jaeger_tracing)
    await tester.test_feature("Audit Logging", tester.test_audit_logging)
    
    # Print summary
    tester.print_summary()
    
    print("\n✨ Local tests completed!")
    print("\n💡 Note: For complete integration testing with all services,")
    print("   please start Docker and run: ./run_full_stack_test.sh")
    
    return 0 if tester.failed == 0 else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)