"""
Comprehensive tests for GraphQL security features
Verifies query depth limiting, complexity analysis, and rate limiting
"""
import pytest
from typing import Dict, Any
from unittest.mock import Mock, AsyncMock, patch
from graphql import parse, GraphQLSchema, GraphQLObjectType, GraphQLField, GraphQLString
import time

from api.graphql.security import (
    SecurityConfig,
    SecurityViolationType,
    QueryDepthValidator,
    QueryComplexityAnalyzer,
    RateLimiter,
    GraphQLSecurityValidator,
    SecurityMiddleware,
    PRODUCTION_SECURITY_CONFIG,
    DEVELOPMENT_SECURITY_CONFIG
)


class TestSecurityConfig:
    """Test security configuration"""
    
    def test_default_config(self):
        """Test default security configuration values"""
        config = SecurityConfig()
        
        assert config.max_depth == 10
        assert config.max_complexity == 1000
        assert config.max_query_size == 10000
        assert config.enable_introspection == False
        assert config.rate_limit_window == 60
        assert config.rate_limit_max_requests == 100
        
        # Check default complexity multipliers
        assert config.complexity_multipliers["search"] == 10
        assert config.complexity_multipliers["aggregate"] == 20
        assert config.complexity_multipliers["export"] == 50
    
    def test_custom_config(self):
        """Test custom security configuration"""
        config = SecurityConfig(
            max_depth=5,
            max_complexity=500,
            complexity_multipliers={"custom": 100}
        )
        
        assert config.max_depth == 5
        assert config.max_complexity == 500
        assert config.complexity_multipliers["custom"] == 100


class TestQueryDepthValidator:
    """Test query depth validation"""
    
    def test_simple_query_within_limit(self):
        """Test query within depth limit"""
        validator = QueryDepthValidator(max_depth=5)
        
        query = parse("""
            query {
                user {
                    id
                    name
                    posts {
                        title
                    }
                }
            }
        """)
        
        # Visit the query
        from graphql.language.visitor import visit
        visit(query, validator)
        
        assert len(validator.errors) == 0
        assert validator.max_depth_reached == 3  # user -> posts -> title
    
    def test_deep_query_exceeds_limit(self):
        """Test query exceeding depth limit"""
        validator = QueryDepthValidator(max_depth=3)
        
        query = parse("""
            query {
                user {
                    posts {
                        author {
                            posts {
                                title
                            }
                        }
                    }
                }
            }
        """)
        
        from graphql.language.visitor import visit
        visit(query, validator)
        
        assert len(validator.errors) > 0
        assert validator.errors[0]["type"] == SecurityViolationType.DEPTH_EXCEEDED
        assert validator.max_depth_reached > 3
    
    def test_fragments_depth(self):
        """Test depth calculation with fragments"""
        validator = QueryDepthValidator(max_depth=4)
        
        query = parse("""
            query {
                user {
                    ...UserDetails
                }
            }
            
            fragment UserDetails on User {
                id
                posts {
                    ...PostDetails
                }
            }
            
            fragment PostDetails on Post {
                title
                author {
                    name
                }
            }
        """)
        
        from graphql.language.visitor import visit
        visit(query, validator)
        
        # Should calculate depth through fragments
        assert validator.max_depth_reached >= 4


class TestQueryComplexityAnalyzer:
    """Test query complexity analysis"""
    
    def test_simple_query_complexity(self):
        """Test complexity calculation for simple query"""
        config = SecurityConfig()
        schema = GraphQLSchema(
            query=GraphQLObjectType(
                "Query",
                fields={
                    "user": GraphQLField(GraphQLString)
                }
            )
        )
        
        analyzer = QueryComplexityAnalyzer(config, schema)
        
        query = parse("""
            query {
                user
            }
        """)
        
        from graphql.language.visitor import visit
        visit(query, analyzer)
        
        assert analyzer.complexity_score == 1  # Base score
        assert len(analyzer.errors) == 0
    
    def test_query_with_multipliers(self):
        """Test complexity with field multipliers"""
        config = SecurityConfig(
            max_complexity=50,
            complexity_multipliers={"search": 10}
        )
        schema = Mock()
        
        analyzer = QueryComplexityAnalyzer(config, schema)
        
        query = parse("""
            query {
                search(query: "test") {
                    results
                }
                normalField
            }
        """)
        
        from graphql.language.visitor import visit
        visit(query, analyzer)
        
        # search: 10 (multiplier) + normalField: 1 + results: 1 = 12
        assert analyzer.complexity_score >= 12
    
    def test_query_with_pagination(self):
        """Test complexity with pagination arguments"""
        config = SecurityConfig(max_complexity=100)
        schema = Mock()
        
        analyzer = QueryComplexityAnalyzer(config, schema)
        
        query = parse("""
            query {
                users(first: 50) {
                    id
                    posts(limit: 10) {
                        title
                    }
                }
            }
        """)
        
        from graphql.language.visitor import visit
        visit(query, analyzer)
        
        # Should multiply by pagination arguments
        # users: 1 * 50 = 50
        # Plus nested fields with their own multipliers
        assert analyzer.complexity_score > 50
    
    def test_exceeding_complexity(self):
        """Test query exceeding complexity limit"""
        config = SecurityConfig(max_complexity=10)
        schema = Mock()
        
        analyzer = QueryComplexityAnalyzer(config, schema)
        
        query = parse("""
            query {
                users(first: 100) {
                    id
                    name
                    email
                }
            }
        """)
        
        from graphql.language.visitor import visit
        visit(query, analyzer)
        
        assert len(analyzer.errors) > 0
        assert analyzer.errors[0]["type"] == SecurityViolationType.COMPLEXITY_EXCEEDED


class TestRateLimiter:
    """Test rate limiting functionality"""
    
    @pytest.mark.asyncio
    async def test_rate_limit_allows_within_limit(self):
        """Test requests within rate limit are allowed"""
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 5  # 5th request
        mock_redis.expire.return_value = True
        
        limiter = RateLimiter(
            redis_client=mock_redis,
            window_seconds=60,
            max_requests=100
        )
        
        allowed = await limiter.check_rate_limit("user123", "query")
        assert allowed == True
        
        mock_redis.incr.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rate_limit_blocks_exceeded(self):
        """Test requests exceeding rate limit are blocked"""
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 101  # 101st request (over limit of 100)
        
        limiter = RateLimiter(
            redis_client=mock_redis,
            window_seconds=60,
            max_requests=100
        )
        
        allowed = await limiter.check_rate_limit("user123", "query")
        assert allowed == False
    
    @pytest.mark.asyncio
    async def test_rate_limit_by_operation(self):
        """Test different rate limits for different operations"""
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 5
        
        limiter = RateLimiter(
            redis_client=mock_redis,
            window_seconds=60,
            max_requests=100,
            operation_limits={
                "mutation": 10,
                "subscription": 5
            }
        )
        
        # Query uses default limit
        allowed = await limiter.check_rate_limit("user123", "query")
        assert allowed == True
        
        # Mutation has lower limit
        mock_redis.incr.return_value = 11
        allowed = await limiter.check_rate_limit("user123", "mutation")
        assert allowed == False
    
    @pytest.mark.asyncio
    async def test_rate_limit_error_handling(self):
        """Test rate limiter handles Redis errors gracefully"""
        mock_redis = AsyncMock()
        mock_redis.incr.side_effect = Exception("Redis connection failed")
        
        limiter = RateLimiter(mock_redis, 60, 100)
        
        # Should allow request on error (fail open)
        allowed = await limiter.check_rate_limit("user123", "query")
        assert allowed == True


class TestGraphQLSecurityValidator:
    """Test the main security validator"""
    
    def test_validate_query_size(self):
        """Test query size validation"""
        config = SecurityConfig(max_query_size=100)
        validator = GraphQLSecurityValidator(config)
        
        # Small query - should pass
        result = validator.validate_query_size("query { user { id } }")
        assert result is None
        
        # Large query - should fail
        large_query = "query { " + "field " * 50 + "}"
        result = validator.validate_query_size(large_query)
        assert result is not None
        assert result["type"] == SecurityViolationType.QUERY_SIZE_EXCEEDED
    
    def test_validate_introspection(self):
        """Test introspection validation"""
        # Production config disables introspection
        validator = GraphQLSecurityValidator(PRODUCTION_SECURITY_CONFIG)
        
        introspection_query = """
            query {
                __schema {
                    types {
                        name
                    }
                }
            }
        """
        
        result = validator.validate_introspection(parse(introspection_query))
        assert result is not None
        assert result["type"] == SecurityViolationType.INTROSPECTION_DISABLED
        
        # Development allows introspection
        dev_validator = GraphQLSecurityValidator(DEVELOPMENT_SECURITY_CONFIG)
        result = dev_validator.validate_introspection(parse(introspection_query))
        assert result is None
    
    @pytest.mark.asyncio
    async def test_validate_all(self):
        """Test complete validation flow"""
        mock_redis = AsyncMock()
        mock_redis.incr.return_value = 1
        
        config = SecurityConfig(
            max_depth=5,
            max_complexity=100
        )
        
        schema = GraphQLSchema(
            query=GraphQLObjectType(
                "Query",
                fields={
                    "user": GraphQLField(GraphQLString)
                }
            )
        )
        
        validator = GraphQLSecurityValidator(
            config,
            schema=schema,
            redis_client=mock_redis
        )
        
        # Valid query
        errors = await validator.validate(
            """
            query {
                user
            }
            """,
            user_id="user123"
        )
        
        assert len(errors) == 0
        
        # Invalid query (too deep)
        deep_query = "query { " + "user { " * 10 + "id" + " }" * 10 + " }"
        errors = await validator.validate(deep_query, user_id="user123")
        
        assert len(errors) > 0


class TestSecurityMiddleware:
    """Test security middleware integration"""
    
    @pytest.mark.asyncio
    async def test_middleware_blocks_invalid_queries(self):
        """Test middleware blocks security violations"""
        mock_validator = AsyncMock()
        mock_validator.validate.return_value = [{
            "type": SecurityViolationType.DEPTH_EXCEEDED,
            "message": "Query too deep"
        }]
        
        middleware = SecurityMiddleware(mock_validator)
        
        # Mock GraphQL context
        mock_info = Mock()
        mock_info.context = {"user_id": "user123"}
        
        # Should raise exception
        with pytest.raises(Exception) as exc_info:
            await middleware.process_query(
                "query { deep }",
                mock_info
            )
        
        assert "Query too deep" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_middleware_allows_valid_queries(self):
        """Test middleware allows valid queries"""
        mock_validator = AsyncMock()
        mock_validator.validate.return_value = []  # No errors
        
        middleware = SecurityMiddleware(mock_validator)
        
        mock_info = Mock()
        mock_info.context = {"user_id": "user123"}
        
        # Should not raise
        result = await middleware.process_query(
            "query { user }",
            mock_info
        )
        
        assert result is None  # Passes through


class TestProductionVsDevelopment:
    """Test differences between production and development configs"""
    
    def test_production_config(self):
        """Test production security is strict"""
        assert PRODUCTION_SECURITY_CONFIG.enable_introspection == False
        assert PRODUCTION_SECURITY_CONFIG.max_depth <= 10
        assert PRODUCTION_SECURITY_CONFIG.max_complexity <= 1000
        assert PRODUCTION_SECURITY_CONFIG.rate_limit_max_requests <= 100
    
    def test_development_config(self):
        """Test development security is relaxed"""
        assert DEVELOPMENT_SECURITY_CONFIG.enable_introspection == True
        assert DEVELOPMENT_SECURITY_CONFIG.max_depth >= 15
        assert DEVELOPMENT_SECURITY_CONFIG.max_complexity >= 5000
        assert DEVELOPMENT_SECURITY_CONFIG.rate_limit_max_requests >= 1000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])