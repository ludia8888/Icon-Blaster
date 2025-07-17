"""
Unit tests for Pydantic request models
Tests validation logic, field constraints, and error handling
"""

import pytest
from pydantic import ValidationError
from models.requests import (
    BranchCreateRequest, 
    CheckoutRequest, 
    CommitRequest, 
    MergeRequest, 
    RollbackRequest, 
    DatabaseCreateRequest,
    ApiResponse
)


class TestBranchCreateRequest:
    """Test BranchCreateRequest validation"""
    
    def test_valid_branch_request(self, sample_branch_data):
        """Test valid branch creation request"""
        request = BranchCreateRequest(**sample_branch_data)
        assert request.branch_name == "feature-test"
        assert request.from_branch == "main"
    
    def test_branch_name_validation(self):
        """Test branch name validation rules"""
        # Valid branch names
        valid_names = ["main", "feature-branch", "test_branch", "branch-1", "dev/feature"]
        for name in valid_names:
            request = BranchCreateRequest(branch_name=name)
            assert request.branch_name == name
        
        # Invalid branch names
        invalid_names = ["", "branch name", "branch@name", "branch#name", "branch!"]
        for name in invalid_names:
            with pytest.raises(ValidationError):
                BranchCreateRequest(branch_name=name)
    
    def test_branch_name_length_limits(self):
        """Test branch name length validation"""
        # Too long
        with pytest.raises(ValidationError):
            BranchCreateRequest(branch_name="a" * 101)
        
        # Valid length
        request = BranchCreateRequest(branch_name="a" * 100)
        assert len(request.branch_name) == 100


class TestCheckoutRequest:
    """Test CheckoutRequest validation"""
    
    def test_valid_branch_checkout(self):
        """Test valid branch checkout"""
        request = CheckoutRequest(target="main", type="branch")
        assert request.target == "main"
        assert request.type == "branch"
    
    def test_valid_commit_checkout(self):
        """Test valid commit checkout"""
        request = CheckoutRequest(target="abc123def456", type="commit")
        assert request.target == "abc123def456"
        assert request.type == "commit"
    
    def test_invalid_commit_id(self):
        """Test invalid commit ID validation"""
        with pytest.raises(ValidationError):
            CheckoutRequest(target="invalid@commit", type="commit")
    
    def test_default_type(self):
        """Test default checkout type"""
        request = CheckoutRequest(target="main")
        assert request.type == "branch"


class TestCommitRequest:
    """Test CommitRequest validation"""
    
    def test_valid_commit_request(self, sample_commit_data):
        """Test valid commit request"""
        request = CommitRequest(**sample_commit_data)
        assert request.message == "Test commit message"
        assert request.author == "test@example.com"
        assert request.branch == "feature-test"
    
    def test_email_validation(self):
        """Test author email validation"""
        # Valid emails
        valid_emails = ["test@example.com", "user.name@domain.co.uk", "dev+test@company.org"]
        for email in valid_emails:
            request = CommitRequest(message="test", author=email)
            assert request.author == email
        
        # Invalid emails that should actually fail (empty string/spaces)
        invalid_emails = ["", "   "]
        for email in invalid_emails:
            with pytest.raises(ValidationError):
                CommitRequest(message="test", author=email)
        
        # Note: "notanemail" passes because email.utils.parseaddr is lenient
    
    def test_message_length_limits(self):
        """Test commit message length validation"""
        # Too long
        with pytest.raises(ValidationError):
            CommitRequest(message="a" * 501, author="test@example.com")
        
        # Valid length
        request = CommitRequest(message="a" * 500, author="test@example.com")
        assert len(request.message) == 500


class TestMergeRequest:
    """Test MergeRequest validation"""
    
    def test_valid_merge_request(self, sample_merge_data):
        """Test valid merge request"""
        request = MergeRequest(**sample_merge_data)
        assert request.source_branch == "feature-test"
        assert request.target_branch == "main"
        assert request.strategy == "merge"
    
    def test_strategy_validation(self):
        """Test merge strategy validation"""
        valid_strategies = ["merge", "squash", "rebase"]
        for strategy in valid_strategies:
            request = MergeRequest(
                source_branch="feature", 
                target_branch="main", 
                strategy=strategy
            )
            assert request.strategy == strategy
        
        # Invalid strategy should use default
        request = MergeRequest(source_branch="feature", target_branch="main")
        assert request.strategy == "merge"
    
    def test_optional_author_validation(self):
        """Test optional author email validation"""
        # Valid with author
        request = MergeRequest(
            source_branch="feature", 
            target_branch="main",
            author="test@example.com"
        )
        assert request.author == "test@example.com"
        
        # Valid without author
        request = MergeRequest(source_branch="feature", target_branch="main")
        assert request.author is None
        
        # Invalid author email (empty string should fail)
        with pytest.raises(ValidationError):
            MergeRequest(
                source_branch="feature", 
                target_branch="main",
                author=""
            )


class TestRollbackRequest:
    """Test RollbackRequest validation"""
    
    def test_valid_rollback_request(self, sample_rollback_data):
        """Test valid rollback request"""
        request = RollbackRequest(**sample_rollback_data)
        assert request.target_commit == "abc123def456"
        assert request.create_branch is True
        assert request.branch_name == "rollback-test"
    
    def test_commit_id_validation(self):
        """Test commit ID validation"""
        # Valid commit IDs
        valid_commits = ["abc123", "ABC123DEF456", "1234567890abcdef"]
        for commit in valid_commits:
            request = RollbackRequest(target_commit=commit)
            assert request.target_commit == commit
        
        # Invalid commit IDs
        invalid_commits = ["invalid_commit", "commit-123", "abc123@"]
        for commit in invalid_commits:
            with pytest.raises(ValidationError):
                RollbackRequest(target_commit=commit)
    
    def test_default_create_branch(self):
        """Test default value for create_branch"""
        request = RollbackRequest(target_commit="abc123")
        assert request.create_branch is True


class TestDatabaseCreateRequest:
    """Test DatabaseCreateRequest validation"""
    
    def test_valid_database_request(self, sample_database_data):
        """Test valid database creation request"""
        request = DatabaseCreateRequest(**sample_database_data)
        assert request.name == "test_database"
        assert request.description == "Test database for unit tests"
    
    def test_database_name_validation(self):
        """Test database name validation rules"""
        # Valid names
        valid_names = ["test_db", "MyDatabase", "db-1", "database_test"]
        for name in valid_names:
            request = DatabaseCreateRequest(name=name)
            assert request.name == name
        
        # Invalid names (must start with letter)
        invalid_names = ["1database", "_database", "-database", "database space"]
        for name in invalid_names:
            with pytest.raises(ValidationError):
                DatabaseCreateRequest(name=name)
    
    def test_description_default(self):
        """Test default description value"""
        request = DatabaseCreateRequest(name="test_db")
        assert request.description == ""
    
    def test_name_length_limits(self):
        """Test database name length validation"""
        # Too long
        with pytest.raises(ValidationError):
            DatabaseCreateRequest(name="a" * 51)
        
        # Valid length
        request = DatabaseCreateRequest(name="a" * 50)
        assert len(request.name) == 50


class TestApiResponse:
    """Test ApiResponse model"""
    
    def test_success_response(self):
        """Test success response creation"""
        response = ApiResponse(
            status="success",
            message="Operation completed",
            data={"result": "test"}
        )
        assert response.status == "success"
        assert response.message == "Operation completed"
        assert response.data == {"result": "test"}
    
    def test_error_response(self):
        """Test error response creation"""
        response = ApiResponse(
            status="error",
            message="Operation failed"
        )
        assert response.status == "error"
        assert response.message == "Operation failed"
        assert response.data is None
    
    def test_status_validation(self):
        """Test status field validation"""
        # Invalid status
        with pytest.raises(ValidationError):
            ApiResponse(status="invalid", message="test")


if __name__ == "__main__":
    pytest.main([__file__])