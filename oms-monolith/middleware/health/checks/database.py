"""
Database health check implementation
"""
import asyncio
from typing import Optional, Any
from .base import HealthCheck
from ..models import HealthCheckResult, HealthStatus


class DatabaseHealthCheck(HealthCheck):
    """Health check for database connectivity and performance"""
    
    def __init__(
        self,
        connection_string: str,
        name: str = "database",
        timeout: float = 5.0,
        query: str = "SELECT 1"
    ):
        super().__init__(name, timeout)
        self.connection_string = connection_string
        self.query = query
        self._connection = None
    
    async def check(self) -> HealthCheckResult:
        """Check database health"""
        try:
            # Import database library dynamically
            try:
                import asyncpg
                return await self._check_postgres()
            except ImportError:
                pass
            
            try:
                import aiomysql
                return await self._check_mysql()
            except ImportError:
                pass
            
            # Fallback for generic check
            return await self._check_generic()
            
        except Exception as e:
            return self.create_result(
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {str(e)}",
                details={"error": str(e)}
            )
    
    async def _check_postgres(self) -> HealthCheckResult:
        """PostgreSQL specific health check"""
        import asyncpg
        
        try:
            # Test connection
            conn = await asyncio.wait_for(
                asyncpg.connect(self.connection_string),
                timeout=self.timeout
            )
            
            try:
                # Execute test query
                result = await conn.fetchval(self.query)
                
                # Get connection pool stats if available
                pool_stats = {}
                if hasattr(conn, '_pool'):
                    pool = conn._pool
                    pool_stats = {
                        "size": pool.get_size(),
                        "free": pool.get_idle_size(),
                        "used": pool.get_size() - pool.get_idle_size()
                    }
                
                return self.create_result(
                    status=HealthStatus.HEALTHY,
                    message="PostgreSQL connection successful",
                    details={
                        "query_result": result,
                        "pool_stats": pool_stats,
                        "database": "postgresql"
                    }
                )
                
            finally:
                await conn.close()
                
        except asyncio.TimeoutError:
            return self.create_result(
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection timeout ({self.timeout}s)",
                details={"timeout": self.timeout}
            )
        except Exception as e:
            return self.create_result(
                status=HealthStatus.UNHEALTHY,
                message=f"PostgreSQL error: {str(e)}",
                details={"error": str(e), "database": "postgresql"}
            )
    
    async def _check_mysql(self) -> HealthCheckResult:
        """MySQL specific health check"""
        import aiomysql
        
        try:
            # Parse connection string
            # This is simplified - real implementation would parse properly
            conn = await asyncio.wait_for(
                aiomysql.connect(
                    host='localhost',
                    port=3306,
                    user='user',
                    password='password',
                    db='database'
                ),
                timeout=self.timeout
            )
            
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute(self.query)
                    result = await cursor.fetchone()
                
                return self.create_result(
                    status=HealthStatus.HEALTHY,
                    message="MySQL connection successful",
                    details={
                        "query_result": result,
                        "database": "mysql"
                    }
                )
                
            finally:
                conn.close()
                
        except asyncio.TimeoutError:
            return self.create_result(
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection timeout ({self.timeout}s)",
                details={"timeout": self.timeout}
            )
        except Exception as e:
            return self.create_result(
                status=HealthStatus.UNHEALTHY,
                message=f"MySQL error: {str(e)}",
                details={"error": str(e), "database": "mysql"}
            )
    
    async def _check_generic(self) -> HealthCheckResult:
        """Generic database health check"""
        # This would use a generic database interface
        return self.create_result(
            status=HealthStatus.UNKNOWN,
            message="No specific database driver available",
            details={"supported": ["postgresql", "mysql"]}
        )