"""
Import 테스트 - 순환 참조 및 import 오류 확인
"""
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """각 모듈의 import 테스트"""
    
    print("Testing shared modules...")
    try:
        from shared.cache.smart_cache import SmartCacheManager
        print("✓ SmartCacheManager imported")
    except Exception as e:
        print(f"✗ SmartCacheManager import failed: {e}")
    
    try:
        from database.clients.terminus_db import TerminusDBClient
        print("✓ TerminusDBClient imported")
    except Exception as e:
        print(f"✗ TerminusDBClient import failed: {e}")
    
    try:
        from shared.events import EventPublisher
        print("✓ EventPublisher imported")
    except Exception as e:
        print(f"✗ EventPublisher import failed: {e}")
    
    print("\nTesting core modules...")
    
    try:
        from core.schema.service import SchemaService
        print("✓ SchemaService imported")
    except Exception as e:
        print(f"✗ SchemaService import failed: {e}")
    
    try:
        from core.branch.service import BranchService
        print("✓ BranchService imported")
    except Exception as e:
        print(f"✗ BranchService import failed: {e}")
    
    try:
        from core.validation.service import ValidationService
        print("✓ ValidationService imported")
    except Exception as e:
        print(f"✗ ValidationService import failed: {e}")
    
    print("\nTesting models...")
    
    try:
        from shared.models.domain import ObjectType, Property, LinkType
        print("✓ Domain models imported")
    except Exception as e:
        print(f"✗ Domain models import failed: {e}")

if __name__ == "__main__":
    test_imports()