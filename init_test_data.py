#!/usr/bin/env python3
"""
Initialize test data for integration testing
Creates test users and sets up initial data
"""
import asyncio
import sys
from datetime import datetime, timezone
from sqlalchemy import create_engine, text
from passlib.context import CryptContext

# Database URLs
USER_DB_URL = "postgresql://user_service:user_password@localhost:5433/userdb"
OMS_DB_URL = "postgresql://oms_user:oms_password@localhost:5432/oms_db"

# Password hashing
pwd_context = CryptContext(schemes=["argon2", "bcrypt"], default="argon2")


async def init_user_service_db():
    """Initialize User Service database with test data"""
    print("Initializing User Service database...")
    
    engine = create_engine(USER_DB_URL.replace("+asyncpg", ""))
    
    try:
        with engine.connect() as conn:
            # Create tables if not exists (simplified)
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    id VARCHAR PRIMARY KEY,
                    username VARCHAR UNIQUE NOT NULL,
                    email VARCHAR UNIQUE NOT NULL,
                    password_hash VARCHAR NOT NULL,
                    full_name VARCHAR,
                    tenant_id VARCHAR,
                    status VARCHAR DEFAULT 'active',
                    roles TEXT[] DEFAULT '{}',
                    permissions TEXT[] DEFAULT '{}',
                    teams TEXT[] DEFAULT '{}',
                    mfa_enabled BOOLEAN DEFAULT FALSE,
                    failed_login_attempts INTEGER DEFAULT 0,
                    last_login TIMESTAMP WITH TIME ZONE,
                    last_activity TIMESTAMP WITH TIME ZONE,
                    locked_until TIMESTAMP WITH TIME ZONE,
                    last_failed_login TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            conn.commit()
            
            # Create test users
            test_users = [
                {
                    "id": "test-user-001",
                    "username": "test_user",
                    "email": "test@example.com",
                    "password": "Test123!@#",
                    "full_name": "Test User",
                    "roles": ["developer"],
                    "tenant_id": "test-tenant"
                },
                {
                    "id": "admin-user-001",
                    "username": "admin",
                    "email": "admin@example.com",
                    "password": "Admin123!@#",
                    "full_name": "Admin User",
                    "roles": ["admin"],
                    "tenant_id": "test-tenant"
                },
                {
                    "id": "reviewer-user-001",
                    "username": "reviewer",
                    "email": "reviewer@example.com",
                    "password": "Review123!@#",
                    "full_name": "Reviewer User",
                    "roles": ["reviewer"],
                    "tenant_id": "test-tenant"
                }
            ]
            
            for user in test_users:
                # Hash password
                password_hash = pwd_context.hash(user["password"])
                
                # Insert user
                conn.execute(text("""
                    INSERT INTO users (
                        id, username, email, password_hash, full_name,
                        tenant_id, roles, created_at, updated_at
                    ) VALUES (
                        :id, :username, :email, :password_hash, :full_name,
                        :tenant_id, :roles, NOW(), NOW()
                    )
                    ON CONFLICT (username) DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        roles = EXCLUDED.roles,
                        updated_at = NOW()
                """), {
                    "id": user["id"],
                    "username": user["username"],
                    "email": user["email"],
                    "password_hash": password_hash,
                    "full_name": user["full_name"],
                    "tenant_id": user["tenant_id"],
                    "roles": user["roles"]
                })
            conn.commit()
            
            print("✓ User Service database initialized with test users")
            
    except Exception as e:
        print(f"✗ Error initializing User Service database: {e}")
        return False
    
    return True


async def init_oms_db():
    """Initialize OMS database"""
    print("\nInitializing OMS database...")
    
    engine = create_engine(OMS_DB_URL.replace("+asyncpg", ""))
    
    try:
        with engine.connect() as conn:
            # Create basic tables if needed
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS branches (
                    id VARCHAR PRIMARY KEY,
                    name VARCHAR NOT NULL,
                    description TEXT,
                    created_by VARCHAR,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))
            conn.commit()
            
            print("✓ OMS database initialized")
            
    except Exception as e:
        print(f"✗ Error initializing OMS database: {e}")
        return False
    
    return True


async def main():
    """Initialize all databases"""
    print("=" * 60)
    print("Initializing Test Data")
    print("=" * 60)
    
    # Wait a bit for databases to be ready
    print("Waiting for databases to be ready...")
    await asyncio.sleep(5)
    
    # Initialize databases
    user_db_success = await init_user_service_db()
    oms_db_success = await init_oms_db()
    
    if user_db_success and oms_db_success:
        print("\n✓ All databases initialized successfully!")
        print("\nTest Users:")
        print("  - Username: test_user, Password: Test123!@#, Role: developer")
        print("  - Username: admin, Password: Admin123!@#, Role: admin")
        print("  - Username: reviewer, Password: Review123!@#, Role: reviewer")
        return 0
    else:
        print("\n✗ Database initialization failed")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))