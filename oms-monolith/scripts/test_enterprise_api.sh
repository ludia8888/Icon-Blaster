#!/bin/bash

echo "🏢 OMS 엔터프라이즈급 API 통합 테스트"
echo "=========================================="

# 1. 헬스체크
echo -e "\n1️⃣ 시스템 헬스체크"
curl -s http://localhost:8002/health | jq .

# 2. 현재 ObjectType 목록
echo -e "\n2️⃣ 현재 ObjectType 목록 (실제 DB)"
curl -s http://localhost:8002/api/v1/schemas/main/object-types | jq .

# 3. 새로운 엔터프라이즈 도메인 모델 생성
echo -e "\n3️⃣ 엔터프라이즈 도메인 모델 생성"

# 3.1 Invoice 타입
echo -e "\n  - Invoice 타입 생성"
curl -s -X POST http://localhost:8002/api/v1/schemas/main/object-types \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Invoice",
    "displayName": "송장",
    "description": "고객 송장 정보를 관리하는 엔터프라이즈 도메인 모델"
  }' | jq .

# 3.2 Payment 타입
echo -e "\n  - Payment 타입 생성"
curl -s -X POST http://localhost:8002/api/v1/schemas/main/object-types \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Payment",
    "displayName": "결제",
    "description": "결제 트랜잭션 정보"
  }' | jq .

# 3.3 Inventory 타입
echo -e "\n  - Inventory 타입 생성"
curl -s -X POST http://localhost:8002/api/v1/schemas/main/object-types \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Inventory",
    "displayName": "재고",
    "description": "상품 재고 관리"
  }' | jq .

# 4. 최종 ObjectType 목록 확인
echo -e "\n4️⃣ 최종 ObjectType 목록 (엔터프라이즈 도메인 추가 확인)"
curl -s http://localhost:8002/api/v1/schemas/main/object-types | jq '.objectTypes | length as $count | {total_count: $count, types: [.[] | {name, description}]}'

echo -e "\n✅ 엔터프라이즈 API 테스트 완료!"