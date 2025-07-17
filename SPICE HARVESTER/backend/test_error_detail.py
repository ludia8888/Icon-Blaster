#!/usr/bin/env python3
"""
Test Error Detail
"""

import httpx
import asyncio

async def test_error():
    """Get detailed error"""
    
    async with httpx.AsyncClient(timeout=30) as client:
        # Use existing database
        response = await client.get(
            "http://localhost:8002/database/testlang/ontology/TestClass"
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

if __name__ == "__main__":
    asyncio.run(test_error())