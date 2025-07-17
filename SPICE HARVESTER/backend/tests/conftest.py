"""
Shared test configuration and fixtures
"""

import pytest
import sys
import os
from pathlib import Path

# Add backend directories to path
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root / "shared"))
sys.path.insert(0, str(backend_root / "backend-for-frontend"))
sys.path.insert(0, str(backend_root / "ontology-management-service"))

@pytest.fixture
def sample_branch_data():
    """Sample data for branch operations"""
    return {
        "branch_name": "feature-test",
        "from_branch": "main"
    }

@pytest.fixture
def sample_commit_data():
    """Sample data for commit operations"""
    return {
        "message": "Test commit message",
        "author": "test@example.com",
        "branch": "feature-test"
    }

@pytest.fixture
def sample_merge_data():
    """Sample data for merge operations"""
    return {
        "source_branch": "feature-test",
        "target_branch": "main",
        "strategy": "merge",
        "message": "Merge feature-test into main",
        "author": "test@example.com"
    }

@pytest.fixture
def sample_rollback_data():
    """Sample data for rollback operations"""
    return {
        "target_commit": "abc123def456",
        "create_branch": True,
        "branch_name": "rollback-test"
    }

@pytest.fixture
def sample_database_data():
    """Sample data for database creation"""
    return {
        "name": "test_database",
        "description": "Test database for unit tests"
    }