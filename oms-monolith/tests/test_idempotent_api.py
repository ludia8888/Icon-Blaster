"""
Tests for Idempotent Consumer API endpoints
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timezone

from models.idempotency import generate_event_id


@pytest.fixture
def client():
    """Create test client"""
    from main import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Create auth headers for testing"""
    import jwt
    from datetime import datetime, timedelta, timezone
    
    # Create a valid JWT token for testing
    secret = "your-secret-key"  # Same as in UserServiceClient
    payload = {
        "sub": "test-user",
        "user_id": "test-user",
        "username": "testuser",
        "email": "test@example.com",
        "roles": ["admin", "developer"],
        "tenant_id": "test-tenant",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc)
    }
    
    token = jwt.encode(payload, secret, algorithm="HS256")
    
    return {
        "Authorization": f"Bearer {token}",
        "X-User-ID": "test-user",
        "X-User-Email": "test@example.com",
        "X-User-Name": "Test User",
        "X-User-Roles": "admin,developer"
    }


class TestIdempotentAPI:
    """Test idempotent consumer API endpoints"""
    
    def test_process_single_event(self, client, auth_headers):
        """Test processing a single event"""
        response = client.post(
            "/api/v1/idempotent/process",
            json={
                "event_type": "object_type.created",
                "payload": {
                    "type_id": "Employee",
                    "type_data": {
                        "name": "Employee",
                        "description": "Employee object type"
                    }
                }
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["processed"] == True
        assert data["was_duplicate"] == False
        assert data["event_id"] is not None
        assert data["commit_transition"]["from"] is not None
        assert data["commit_transition"]["to"] is not None
        assert data["processing_time_ms"] > 0
        assert len(data["side_effects"]) > 0
    
    def test_idempotent_processing(self, client, auth_headers):
        """Test that duplicate events are not processed twice"""
        # Process first time
        event_id = generate_event_id()
        
        response1 = client.post(
            "/api/v1/idempotent/process",
            json={
                "event_id": event_id,
                "event_type": "object_type.created",
                "payload": {
                    "type_id": "Department",
                    "type_data": {
                        "name": "Department"
                    }
                }
            },
            headers=auth_headers
        )
        
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["processed"] == True
        assert data1["was_duplicate"] == False
        
        # Process again (should be duplicate)
        response2 = client.post(
            "/api/v1/idempotent/process",
            json={
                "event_id": event_id,
                "event_type": "object_type.created",
                "payload": {
                    "type_id": "Department",
                    "type_data": {
                        "name": "Department"
                    }
                }
            },
            headers=auth_headers
        )
        
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["processed"] == False
        assert data2["was_duplicate"] == True
        
        # Commit hashes should match
        assert data2["commit_transition"] == data1["commit_transition"]
    
    def test_process_batch(self, client, auth_headers):
        """Test processing multiple events as a batch"""
        response = client.post(
            "/api/v1/idempotent/process-batch",
            json={
                "events": [
                    {
                        "event_type": "object_type.created",
                        "payload": {
                            "type_id": f"Type{i}",
                            "type_data": {"name": f"Type{i}"}
                        }
                    }
                    for i in range(5)
                ],
                "stop_on_error": False
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["batch_size"] == 5
        assert data["processed"] == 5
        assert data["duplicates"] == 0
        assert data["errors"] == 0
        assert len(data["results"]) == 5
        
        # All should be processed
        for result in data["results"]:
            assert result["processed"] == True
            assert result["was_duplicate"] == False
    
    def test_get_consumer_status(self, client, auth_headers):
        """Test getting consumer status"""
        response = client.get(
            "/api/v1/idempotent/consumers/schema_consumer/status",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["consumer_id"] == "schema_consumer"
        assert data["consumer_version"] is not None
        assert "object_types" in data["state"]
        assert "events_processed" in data["processing"]
        assert data["health"]["is_healthy"] == True
    
    def test_get_consumer_state(self, client, auth_headers):
        """Test getting consumer state"""
        response = client.get(
            "/api/v1/idempotent/consumers/schema_consumer/state",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["consumer_id"] == "schema_consumer"
        assert "state" in data
        assert "state_hash" in data
        assert "state_version" in data
        
        # State should contain schema info
        state = data["state"]
        assert "object_types" in state
        assert "link_types" in state
        assert "schema_version" in state
    
    def test_create_checkpoint(self, client, auth_headers):
        """Test manually creating a checkpoint"""
        response = client.post(
            "/api/v1/idempotent/consumers/schema_consumer/checkpoint",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] == True
        assert "Checkpoint created" in data["message"]
        assert data["state_version"] is not None
    
    def test_generate_test_events(self, client, auth_headers):
        """Test generating test events"""
        # Reset schema first
        reset_response = client.post(
            "/api/v1/idempotent/test/generate-events?event_type=schema.reset&count=1",
            headers=auth_headers
        )
        assert reset_response.status_code == 200
        
        # Generate object type events
        response = client.post(
            "/api/v1/idempotent/test/generate-events?event_type=object_type.created&count=10",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["generated"] == 10
        assert data["processed"] == 10
        assert data["duplicates"] == 0
        assert data["state_after"]["object_types"] == 10
        assert data["state_after"]["schema_version"] > 0
    
    def test_start_replay(self, client, auth_headers):
        """Test starting event replay"""
        response = client.post(
            "/api/v1/idempotent/replay",
            json={
                "consumer_id": "schema_consumer",
                "skip_side_effects": True,
                "dry_run": True
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["replay_id"] is not None
        assert data["status"] == "started"
        assert data["consumer_id"] == "schema_consumer"
        assert data["options"]["skip_side_effects"] == True
        assert data["options"]["dry_run"] == True
    
    def test_get_replay_status(self, client, auth_headers):
        """Test getting replay status"""
        # Start a replay first
        start_response = client.post(
            "/api/v1/idempotent/replay",
            json={"consumer_id": "schema_consumer"},
            headers=auth_headers
        )
        replay_id = start_response.json()["replay_id"]
        
        # Get status
        response = client.get(
            f"/api/v1/idempotent/replay/{replay_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["replay_id"] == replay_id
        assert data["status"] in ["started", "completed", "failed"]
        assert data["events_replayed"] >= 0
        assert data["events_skipped"] >= 0
        assert data["started_at"] is not None
    
    def test_consumer_not_found(self, client, auth_headers):
        """Test accessing non-existent consumer"""
        response = client.get(
            "/api/v1/idempotent/consumers/non_existent/status",
            headers=auth_headers
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]
    
    def test_invalid_event_type(self, client, auth_headers):
        """Test generating events with invalid type"""
        response = client.post(
            "/api/v1/idempotent/test/generate-events?event_type=invalid.type&count=1",
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "Unknown event type" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])