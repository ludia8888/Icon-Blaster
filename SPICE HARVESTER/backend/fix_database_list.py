#!/usr/bin/env python3
"""
Fix for database list not showing newly created databases.
The issue is in how the TerminusDB response is parsed.
"""

import json

# Sample fix for async_terminus.py list_databases method
fix_code = '''
    async def list_databases(self) -> List[Dict[str, Any]]:
        """사용 가능한 데이터베이스 목록 조회"""
        try:
            endpoint = f"/api/db/{self.connection_info.account}"
            result = await self._make_request("GET", endpoint)
            
            # Debug logging
            logger.debug(f"TerminusDB list response type: {type(result)}")
            logger.debug(f"TerminusDB list response: {json.dumps(result, indent=2)}")
            
            databases = []
            
            # TerminusDB may return different formats
            if isinstance(result, list):
                db_list = result
            elif isinstance(result, dict):
                # Check common keys for database list
                if "databases" in result:
                    db_list = result["databases"]
                elif "dbs" in result:
                    db_list = result["dbs"]
                elif "@graph" in result:
                    db_list = result["@graph"]
                else:
                    # If result is a dict with database names as keys
                    db_list = list(result.keys())
            else:
                db_list = []
            
            for db_info in db_list:
                # Process database info...
'''

print("Issue Analysis:")
print("-" * 60)
print("The problem is that the list_databases method may not be correctly parsing")
print("the TerminusDB response format. TerminusDB might return the database list")
print("in a dictionary format rather than a direct list.")
print()
print("Potential fixes:")
print("1. Add debug logging to see actual TerminusDB response format")
print("2. Handle dictionary responses that might contain the database list")
print("3. Check for common keys like 'databases', 'dbs', '@graph'")
print("4. Ensure the test checks for database names correctly in the returned format")