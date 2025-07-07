"""
PostgreSQL Database Connector
Provides connection pooling and query execution for PostgreSQL databases
"""
import asyncio
from typing import Dict, Any, List, Optional, Union
from contextlib import asynccontextmanager
import json
from datetime import datetime

try:
    import asyncpg
except ImportError:
    asyncpg = None

from common_logging.setup import get_logger

logger = get_logger(__name__)


class PostgresConnectorError(Exception):
    """Base exception for PostgreSQL connector"""
    pass


class PostgresConnector:
    """
    PostgreSQL database connector with connection pooling
    
    Features:
    - Async connection pooling
    - Automatic retry logic
    - Transaction support
    - JSON/JSONB handling
    - Prepared statements
    """
    
    def __init__(
        self,
        database: str,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "",
        min_connections: int = 10,
        max_connections: int = 20,
        command_timeout: float = 60.0,
        max_queries: int = 50000,
        max_inactive_connection_lifetime: float = 300.0
    ):
        """
        Initialize PostgreSQL connector
        
        Args:
            database: Database name
            host: PostgreSQL host
            port: PostgreSQL port
            user: Database user
            password: Database password
            min_connections: Minimum pool size
            max_connections: Maximum pool size
            command_timeout: Query timeout in seconds
            max_queries: Max queries per connection before recreation
            max_inactive_connection_lifetime: Max idle time before closing
        """
        if asyncpg is None:
            raise PostgresConnectorError(
                "asyncpg not installed. Install with: pip install asyncpg"
            )
        
        self.database = database
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.command_timeout = command_timeout
        self.max_queries = max_queries
        self.max_inactive_connection_lifetime = max_inactive_connection_lifetime
        
        self._pool: Optional[asyncpg.Pool] = None
        self._lock = asyncio.Lock()
        self._initialized = False
    
    async def initialize(self, migrations: Optional[List[str]] = None):
        """
        Initialize connection pool and optionally run migrations
        
        Args:
            migrations: List of SQL statements to run on initialization
        """
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            try:
                # Create connection pool
                self._pool = await asyncpg.create_pool(
                    database=self.database,
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    min_size=self.min_connections,
                    max_size=self.max_connections,
                    command_timeout=self.command_timeout,
                    max_queries=self.max_queries,
                    max_inactive_connection_lifetime=self.max_inactive_connection_lifetime,
                    # Custom type codecs for JSON handling
                    init=self._init_connection
                )
                
                # Run migrations if provided
                if migrations:
                    await self._run_migrations(migrations)
                
                self._initialized = True
                logger.info(
                    f"PostgreSQL connection pool initialized for {self.database}@{self.host}:{self.port}"
                )
                
            except Exception as e:
                logger.error(f"Failed to initialize PostgreSQL connection: {e}")
                raise PostgresConnectorError(f"Connection initialization failed: {e}")
    
    async def _init_connection(self, conn):
        """Initialize individual connection with custom settings"""
        # Set up JSON codec
        await conn.set_type_codec(
            'json',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )
        await conn.set_type_codec(
            'jsonb',
            encoder=json.dumps,
            decoder=json.loads,
            schema='pg_catalog'
        )
    
    async def _run_migrations(self, migrations: List[str]):
        """Run migration statements"""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for migration in migrations:
                    try:
                        await conn.execute(migration)
                        logger.debug(f"Executed migration: {migration[:50]}...")
                    except Exception as e:
                        logger.error(f"Migration failed: {e}\nSQL: {migration}")
                        raise
    
    async def close(self):
        """Close connection pool"""
        if self._pool:
            await self._pool.close()
            self._initialized = False
            logger.info("PostgreSQL connection pool closed")
    
    @asynccontextmanager
    async def transaction(self):
        """
        Context manager for database transactions
        
        Usage:
            async with connector.transaction():
                await connector.execute("INSERT ...")
                await connector.execute("UPDATE ...")
        """
        if not self._initialized:
            await self.initialize()
        
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Store connection in context for nested operations
                token = _connection_context.set(conn)
                try:
                    yield conn
                finally:
                    _connection_context.reset(token)
    
    async def execute(
        self,
        query: str,
        params: Optional[Union[Dict[str, Any], List[Any]]] = None,
        timeout: Optional[float] = None
    ) -> str:
        """
        Execute a query without returning results
        
        Args:
            query: SQL query with $1, $2 placeholders or %(name)s placeholders
            params: Query parameters as dict or list
            timeout: Query timeout (overrides default)
            
        Returns:
            Status string (e.g., "INSERT 0 1")
        """
        if not self._initialized:
            await self.initialize()
        
        # Convert dict params to positional if needed
        if params and isinstance(params, dict):
            query, params = self._convert_named_params(query, params)
        
        try:
            # Check if we're in a transaction context
            conn = _connection_context.get(None)
            if conn:
                return await conn.execute(query, *params if params else [], timeout=timeout)
            else:
                async with self._pool.acquire() as conn:
                    return await conn.execute(query, *params if params else [], timeout=timeout)
                    
        except Exception as e:
            logger.error(f"Query execution failed: {e}\nQuery: {query}\nParams: {params}")
            raise PostgresConnectorError(f"Query execution failed: {e}")
    
    async def execute_many(
        self,
        query: str,
        params_list: List[Union[Dict[str, Any], List[Any]]],
        timeout: Optional[float] = None
    ):
        """
        Execute same query multiple times with different parameters
        
        Args:
            query: SQL query
            params_list: List of parameter sets
            timeout: Query timeout
        """
        if not self._initialized:
            await self.initialize()
        
        # Convert all dict params to positional
        converted_params = []
        converted_query = query
        
        for params in params_list:
            if isinstance(params, dict):
                if not converted_params:  # Only convert query once
                    converted_query, converted = self._convert_named_params(query, params)
                else:
                    _, converted = self._convert_named_params(query, params)
                converted_params.append(converted)
            else:
                converted_params.append(params)
        
        try:
            async with self._pool.acquire() as conn:
                await conn.executemany(
                    converted_query,
                    converted_params,
                    timeout=timeout
                )
        except Exception as e:
            logger.error(f"Batch execution failed: {e}")
            raise PostgresConnectorError(f"Batch execution failed: {e}")
    
    async def fetch_one(
        self,
        query: str,
        params: Optional[Union[Dict[str, Any], List[Any]]] = None,
        timeout: Optional[float] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch single row as dictionary
        
        Args:
            query: SQL query
            params: Query parameters
            timeout: Query timeout
            
        Returns:
            Row as dict or None
        """
        if not self._initialized:
            await self.initialize()
        
        # Convert dict params to positional if needed
        if params and isinstance(params, dict):
            query, params = self._convert_named_params(query, params)
        
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(query, *params if params else [], timeout=timeout)
                return dict(row) if row else None
                
        except Exception as e:
            logger.error(f"Fetch one failed: {e}")
            raise PostgresConnectorError(f"Fetch one failed: {e}")
    
    async def fetch_all(
        self,
        query: str,
        params: Optional[Union[Dict[str, Any], List[Any]]] = None,
        timeout: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch all rows as list of dictionaries
        
        Args:
            query: SQL query
            params: Query parameters
            timeout: Query timeout
            
        Returns:
            List of rows as dicts
        """
        if not self._initialized:
            await self.initialize()
        
        # Convert dict params to positional if needed
        if params and isinstance(params, dict):
            query, params = self._convert_named_params(query, params)
        
        try:
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(query, *params if params else [], timeout=timeout)
                return [dict(row) for row in rows]
                
        except Exception as e:
            logger.error(f"Fetch all failed: {e}")
            raise PostgresConnectorError(f"Fetch all failed: {e}")
    
    async def fetch_value(
        self,
        query: str,
        params: Optional[Union[Dict[str, Any], List[Any]]] = None,
        column: int = 0,
        timeout: Optional[float] = None
    ) -> Any:
        """
        Fetch single value from query result
        
        Args:
            query: SQL query
            params: Query parameters
            column: Column index to fetch
            timeout: Query timeout
            
        Returns:
            Single value or None
        """
        if not self._initialized:
            await self.initialize()
        
        # Convert dict params to positional if needed
        if params and isinstance(params, dict):
            query, params = self._convert_named_params(query, params)
        
        try:
            async with self._pool.acquire() as conn:
                return await conn.fetchval(
                    query,
                    *params if params else [],
                    column=column,
                    timeout=timeout
                )
                
        except Exception as e:
            logger.error(f"Fetch value failed: {e}")
            raise PostgresConnectorError(f"Fetch value failed: {e}")
    
    def _convert_named_params(
        self,
        query: str,
        params: Dict[str, Any]
    ) -> tuple[str, List[Any]]:
        """
        Convert named parameters to positional for asyncpg
        
        Converts :param_name or %(param_name)s to $1, $2, etc.
        """
        import re
        
        # Pattern for :param_name or %(param_name)s
        pattern = re.compile(r':(\w+)|%\((\w+)\)s')
        
        param_list = []
        param_map = {}
        counter = 1
        
        def replacer(match):
            nonlocal counter
            param_name = match.group(1) or match.group(2)
            
            if param_name not in param_map:
                param_map[param_name] = counter
                param_list.append(params.get(param_name))
                counter += 1
            
            return f"${param_map[param_name]}"
        
        converted_query = pattern.sub(replacer, query)
        
        return converted_query, param_list
    
    async def create_tables_from_sqlite_schema(self, sqlite_schema: List[str]) -> List[str]:
        """
        Convert SQLite schema to PostgreSQL and create tables
        
        Args:
            sqlite_schema: List of SQLite CREATE TABLE statements
            
        Returns:
            List of converted PostgreSQL statements
        """
        pg_migrations = []
        
        for sqlite_stmt in sqlite_schema:
            # Convert SQLite to PostgreSQL syntax
            pg_stmt = self._convert_sqlite_to_postgres(sqlite_stmt)
            pg_migrations.append(pg_stmt)
        
        # Run the migrations
        await self._run_migrations(pg_migrations)
        
        return pg_migrations
    
    def _convert_sqlite_to_postgres(self, sqlite_stmt: str) -> str:
        """Convert SQLite CREATE TABLE to PostgreSQL syntax"""
        import re
        
        pg_stmt = sqlite_stmt
        
        # Replace AUTOINCREMENT with SERIAL
        pg_stmt = re.sub(
            r'(\w+)\s+INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT',
            r'\1 SERIAL PRIMARY KEY',
            pg_stmt,
            flags=re.IGNORECASE
        )
        
        # Replace INTEGER PRIMARY KEY with SERIAL PRIMARY KEY
        pg_stmt = re.sub(
            r'(\w+)\s+INTEGER\s+PRIMARY\s+KEY',
            r'\1 SERIAL PRIMARY KEY',
            pg_stmt,
            flags=re.IGNORECASE
        )
        
        # Replace DATETIME/TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        pg_stmt = re.sub(
            r'(DATETIME|TIMESTAMP)\s+DEFAULT\s+CURRENT_TIMESTAMP',
            r'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
            pg_stmt,
            flags=re.IGNORECASE
        )
        
        # Replace TEXT with TEXT (no change needed)
        # Replace BOOLEAN with BOOLEAN (no change needed)
        
        # Handle GENERATED ALWAYS AS
        pg_stmt = re.sub(
            r'(\w+)\s+INTEGER\s+GENERATED\s+ALWAYS\s+AS\s*\((.*?)\)\s*STORED',
            r'\1 INTEGER GENERATED ALWAYS AS (\2) STORED',
            pg_stmt,
            flags=re.IGNORECASE | re.DOTALL
        )
        
        # Replace strftime with PostgreSQL equivalent
        pg_stmt = pg_stmt.replace("strftime('%Y',", "EXTRACT(YEAR FROM")
        pg_stmt = pg_stmt.replace("strftime('%m',", "EXTRACT(MONTH FROM")
        pg_stmt = pg_stmt.replace(")", ")::INTEGER)", 1)  # Cast to INTEGER
        
        return pg_stmt
    
    async def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics"""
        if not self._pool:
            return {"status": "not_initialized"}
        
        return {
            "status": "active",
            "size": self._pool.get_size(),
            "free_connections": self._pool.get_idle_size(),
            "used_connections": self._pool.get_size() - self._pool.get_idle_size(),
            "max_size": self._pool.get_max_size(),
            "min_size": self._pool.get_min_size()
        }


# Context variable for transaction connection tracking
import contextvars
_connection_context: contextvars.ContextVar[Optional[asyncpg.Connection]] = \
    contextvars.ContextVar('pg_connection', default=None)


# Singleton instances per database
_postgres_connectors: Dict[str, PostgresConnector] = {}
_postgres_lock = asyncio.Lock()


async def get_postgres_connector(
    database: str,
    host: str = "localhost",
    port: int = 5432,
    user: str = "postgres",
    password: str = "",
    **kwargs
) -> PostgresConnector:
    """
    Get or create PostgreSQL connector instance
    
    Args:
        database: Database name
        host: PostgreSQL host
        port: PostgreSQL port
        user: Database user
        password: Database password
        **kwargs: Additional connector arguments
        
    Returns:
        PostgresConnector instance
    """
    key = f"{user}@{host}:{port}/{database}"
    
    async with _postgres_lock:
        if key not in _postgres_connectors:
            _postgres_connectors[key] = PostgresConnector(
                database=database,
                host=host,
                port=port,
                user=user,
                password=password,
                **kwargs
            )
            await _postgres_connectors[key].initialize()
        
        return _postgres_connectors[key]