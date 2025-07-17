#!/usr/bin/env python3
"""
간단한 기능 검증 스크립트
"""
import sys
import os
from pathlib import Path

# 경로 설정
# 현재 스크립트 위치에서 backend 디렉토리 찾기
current_dir = Path(__file__).parent
base_dir = current_dir / 'backend'
print(f"Base directory: {base_dir}")
print(f"Base directory exists: {base_dir.exists()}")

# 각 디렉토리 확인
dirs = [
    'shared',
    'ontology-management-service', 
    'backend-for-frontend'
]

for dir_name in dirs:
    dir_path = base_dir / dir_name
    print(f"{dir_name}: {dir_path.exists()}")

# 중요 파일들 확인
files_to_check = [
    'shared/models/ontology.py',
    'shared/utils/jsonld.py',
    'ontology-management-service/main.py',
    'ontology-management-service/services/async_terminus.py',
    'backend-for-frontend/main.py',
    'backend-for-frontend/services/oms_client.py',
    'backend-for-frontend/utils/label_mapper.py'
]

print("\n=== 중요 파일 확인 ===")
for file_path in files_to_check:
    full_path = base_dir / file_path
    print(f"✓ {file_path}: {'존재' if full_path.exists() else '없음'}")

# 간단한 import 테스트
print("\n=== Import 테스트 ===")

try:
    # shared 경로 추가
    sys.path.insert(0, str(base_dir / 'shared'))
    from models.ontology import OntologyCreateRequest
    print("✓ Shared models import 성공")
except Exception as e:
    print(f"✗ Shared models import 실패: {e}")

try:
    # OMS 경로 추가 
    sys.path.insert(0, str(base_dir / 'ontology-management-service'))
    from services.async_terminus import AsyncTerminusService
    print("✓ OMS AsyncTerminusService import 성공")
except Exception as e:
    print(f"✗ OMS AsyncTerminusService import 실패: {e}")

try:
    # BFF 경로 추가
    sys.path.insert(0, str(base_dir / 'backend-for-frontend'))
    from services.oms_client import OMSClient
    print("✓ BFF OMSClient import 성공")
except Exception as e:
    print(f"✗ BFF OMSClient import 실패: {e}")

try:
    from utils.label_mapper import LabelMapper
    print("✓ BFF LabelMapper import 성공")
except Exception as e:
    print(f"✗ BFF LabelMapper import 실패: {e}")

print("\n=== 기본 검증 완료 ===")