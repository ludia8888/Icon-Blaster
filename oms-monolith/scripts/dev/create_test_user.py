#!/usr/bin/env python3
"""
Create a test user for integration testing
"""
import asyncio
import asyncpg
import argon2
import json
from datetime import datetime
import uuid


async def create_test_user():
    """Create a test user in the User Service database"""
    
    # Connect to database
    conn = await asyncpg.connect(
        host='localhost',
        port=15433,
        user='user_user',
        password='user_pass',
        database='user_db'
    )
    
    try:
        # Check if user already exists
        existing = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1",
            'test_user'
        )
        
        if existing:
            print("Test user already exists")
            return
        
        # Hash password using Argon2
        ph = argon2.PasswordHasher()
        password_hash = ph.hash('test_password')
        
        # Create user
        user_id = str(uuid.uuid4())
        await conn.execute("""
            INSERT INTO users (
                id, username, email, full_name, password_hash,
                status, roles, permissions, teams,
                mfa_enabled, failed_login_attempts,
                created_at, created_by
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9,
                $10, $11, $12, $13
            )
        """,
            user_id,
            'test_user',
            'test@example.com',
            'Test User',
            password_hash,
            'active',
            json.dumps(['admin', 'user']),
            json.dumps(['*']),  # All permissions for testing
            json.dumps(['engineering']),
            False,
            0,
            datetime.utcnow(),
            'system'
        )
        
        print(f"Created test user: {user_id}")
        
        # Also create an admin user
        admin_id = str(uuid.uuid4())
        admin_hash = ph.hash('admin123')
        
        existing_admin = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1",
            'admin'
        )
        
        if not existing_admin:
            await conn.execute("""
                INSERT INTO users (
                    id, username, email, full_name, password_hash,
                    status, roles, permissions, teams,
                    mfa_enabled, failed_login_attempts,
                    created_at, created_by
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8, $9,
                    $10, $11, $12, $13
                )
            """,
                admin_id,
                'admin',
                'admin@example.com',
                'Administrator',
                admin_hash,
                'active',
                json.dumps(['admin']),
                json.dumps(['*']),
                json.dumps(['admin']),
                False,
                0,
                datetime.utcnow(),
                'system'
            )
            print(f"Created admin user: {admin_id}")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(create_test_user())