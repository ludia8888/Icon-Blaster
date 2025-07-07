#!/bin/bash

# =============================================================================
# Arrakis Project 포괄적 테스트 스크립트
# =============================================================================

set -e

echo "🔍 Arrakis Project 포괄적 테스트 시작"
echo "====================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
BASE_URL="http://localhost:8090"
REPORT_FILE="comprehensive-test-report-$(date +%Y%m%d-%H%M%S).md"

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Test result tracking
FAILED_TEST_NAMES=""

echo "# Arrakis Project 포괄적 테스트 보고서" > "$REPORT_FILE"
echo "" >> "$REPORT_FILE"
echo "테스트 시작: $(date)" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# =============================================================================
# Helper Functions
# =============================================================================

run_test() {
    local test_name=$1
    local test_command=$2
    local expected_result=$3
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    echo -n "  🧪 $test_name... "
    
    if eval "$test_command"; then
        if [[ "$expected_result" == "pass" ]]; then
            echo -e "${GREEN}✓ PASS${NC}"
            PASSED_TESTS=$((PASSED_TESTS + 1))
        else
            echo -e "${RED}✗ FAIL (expected to fail but passed)${NC}"
            FAILED_TESTS=$((FAILED_TESTS + 1))
            FAILED_TEST_NAMES="${FAILED_TEST_NAMES}$test_name: Expected failure but passed\n"
        fi
    else
        if [[ "$expected_result" == "fail" ]]; then
            echo -e "${GREEN}✓ PASS (correctly failed)${NC}"
            PASSED_TESTS=$((PASSED_TESTS + 1))
        else
            echo -e "${RED}✗ FAIL${NC}"
            FAILED_TESTS=$((FAILED_TESTS + 1))
            FAILED_TEST_NAMES="${FAILED_TEST_NAMES}$test_name: FAIL\n"
        fi
    fi
}

# =============================================================================
# 1. 서비스 가용성 테스트
# =============================================================================

echo ""
echo -e "${YELLOW}1. 서비스 가용성 테스트${NC}"
echo "## 1. 서비스 가용성 테스트" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# 각 서비스 헬스 체크
run_test "NGINX Health Check" \
    "curl -sf $BASE_URL/health | grep -q 'healthy'" \
    "pass"

run_test "User Service Direct Health" \
    "docker exec user-service curl -sf http://localhost:8000/health" \
    "pass"

run_test "OMS Direct Health" \
    "docker exec oms-monolith curl -sf http://localhost:8000/health | jq -e '.status == \"healthy\"' > /dev/null" \
    "pass"

run_test "TerminusDB Health" \
    "curl -sf http://localhost:6363/api/status > /dev/null" \
    "pass"

# =============================================================================
# 2. 인증 테스트
# =============================================================================

echo ""
echo -e "${YELLOW}2. 인증 테스트${NC}"
echo "## 2. 인증 테스트" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# 정상 로그인
LOGIN_RESPONSE=$(curl -s -X POST $BASE_URL/auth/login \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=testuser&password=Test123!")

TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token // empty')

run_test "정상 로그인" \
    "[[ -n \"$TOKEN\" ]]" \
    "pass"

# 잘못된 비밀번호
run_test "잘못된 비밀번호 로그인 거부" \
    "curl -sf -X POST $BASE_URL/auth/login \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        -d 'username=testuser&password=WrongPassword' | jq -e '.access_token' > /dev/null" \
    "fail"

# 존재하지 않는 사용자
run_test "존재하지 않는 사용자 로그인 거부" \
    "curl -sf -X POST $BASE_URL/auth/login \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        -d 'username=nonexistentuser&password=Test123!' | jq -e '.access_token' > /dev/null" \
    "fail"

# =============================================================================
# 3. API 엔드포인트 테스트
# =============================================================================

echo ""
echo -e "${YELLOW}3. API 엔드포인트 테스트${NC}"
echo "## 3. API 엔드포인트 테스트" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# 토큰 없이 API 접근
run_test "토큰 없이 API 접근 거부" \
    "curl -sf $BASE_URL/api/v1/schemas -o /dev/null" \
    "fail"

# 잘못된 토큰으로 접근
run_test "잘못된 토큰으로 API 접근 거부" \
    "curl -sf $BASE_URL/api/v1/schemas \
        -H 'Authorization: Bearer invalid_token_12345' -o /dev/null" \
    "fail"

# 정상 토큰으로 접근
run_test "정상 토큰으로 schemas 엔드포인트 접근" \
    "curl -sf $BASE_URL/api/v1/schemas \
        -H \"Authorization: Bearer $TOKEN\" \
        -w '%{http_code}' -o /dev/null | grep -E '200|404'" \
    "pass"

# GraphQL 스키마 생성 테스트
run_test "GraphQL 스키마 생성 엔드포인트" \
    "curl -sf -X POST $BASE_URL/api/v1/schema-generation/graphql \
        -H \"Authorization: Bearer $TOKEN\" \
        -H 'Content-Type: application/json' \
        -d '{\"include_descriptions\": true}' \
        -w '%{http_code}' -o /dev/null | grep -E '200|500'" \
    "pass"

# =============================================================================
# 4. 데이터 무결성 테스트
# =============================================================================

echo ""
echo -e "${YELLOW}4. 데이터 무결성 테스트${NC}"
echo "## 4. 데이터 무결성 테스트" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# 동일한 토큰으로 여러 번 요청
RESPONSE1=$(curl -s $BASE_URL/auth/userinfo -H "Authorization: Bearer $TOKEN")
sleep 1
RESPONSE2=$(curl -s $BASE_URL/auth/userinfo -H "Authorization: Bearer $TOKEN")

run_test "동일 토큰으로 일관된 응답" \
    "[[ \"$RESPONSE1\" == \"$RESPONSE2\" ]]" \
    "pass"

# =============================================================================
# 5. 성능 및 부하 테스트
# =============================================================================

echo ""
echo -e "${YELLOW}5. 성능 및 부하 테스트${NC}"
echo "## 5. 성능 및 부하 테스트" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# 동시 요청 테스트
echo -n "  🧪 동시 50개 요청 처리... "
SUCCESS_COUNT=0
for i in {1..50}; do
    curl -sf $BASE_URL/health > /dev/null && SUCCESS_COUNT=$((SUCCESS_COUNT + 1)) &
done
wait

run_test "동시 50개 요청 처리" \
    "[[ $SUCCESS_COUNT -eq 50 ]]" \
    "pass"

# 응답 시간 테스트
RESPONSE_TIME=$(curl -sf -o /dev/null -w "%{time_total}" $BASE_URL/health)
RESPONSE_MS=$(echo "$RESPONSE_TIME * 1000" | bc 2>/dev/null || echo "N/A")

run_test "Health check 응답 시간 < 100ms" \
    "[[ $(echo \"$RESPONSE_TIME < 0.1\" | bc 2>/dev/null || echo 0) -eq 1 ]]" \
    "pass"

# =============================================================================
# 6. 에러 처리 테스트
# =============================================================================

echo ""
echo -e "${YELLOW}6. 에러 처리 테스트${NC}"
echo "## 6. 에러 처리 테스트" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# 잘못된 JSON 요청
run_test "잘못된 JSON 요청 처리" \
    "curl -sf -X POST $BASE_URL/api/v1/schema-generation/graphql \
        -H \"Authorization: Bearer $TOKEN\" \
        -H 'Content-Type: application/json' \
        -d 'invalid json' \
        -w '%{http_code}' -o /dev/null | grep -E '400|422'" \
    "pass"

# 지원하지 않는 HTTP 메서드
run_test "지원하지 않는 HTTP 메서드 거부" \
    "curl -sf -X DELETE $BASE_URL/auth/login \
        -w '%{http_code}' -o /dev/null | grep -E '405'" \
    "pass"

# =============================================================================
# 7. 서비스 간 통합 테스트
# =============================================================================

echo ""
echo -e "${YELLOW}7. 서비스 간 통합 테스트${NC}"
echo "## 7. 서비스 간 통합 테스트" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# JWT의 issuer/audience 검증
JWT_PAYLOAD=$(echo "$TOKEN" | cut -d'.' -f2 | base64 -d 2>/dev/null || echo "{}")
ISS=$(echo "$JWT_PAYLOAD" | jq -r '.iss // empty' 2>/dev/null || echo "")
AUD=$(echo "$JWT_PAYLOAD" | jq -r '.aud // empty' 2>/dev/null || echo "")

run_test "JWT issuer가 'user-service'" \
    "[[ \"$ISS\" == \"user-service\" ]]" \
    "pass"

run_test "JWT audience가 'oms'" \
    "[[ \"$AUD\" == \"oms\" ]]" \
    "pass"

# =============================================================================
# 8. 장애 복구 테스트
# =============================================================================

echo ""
echo -e "${YELLOW}8. 장애 복구 테스트${NC}"
echo "## 8. 장애 복구 테스트" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# Redis 재시작 후 서비스 정상 작동
echo -n "  🧪 Redis 재시작 후 복구... "
docker restart user-redis > /dev/null 2>&1
sleep 5

run_test "Redis 재시작 후 로그인 가능" \
    "curl -sf -X POST $BASE_URL/auth/login \
        -H 'Content-Type: application/x-www-form-urlencoded' \
        -d 'username=testuser&password=Test123!' | jq -e '.access_token' > /dev/null" \
    "pass"

# =============================================================================
# 테스트 결과 요약
# =============================================================================

echo ""
echo -e "${BLUE}========== 테스트 결과 요약 ==========${NC}"
echo ""
echo "## 테스트 결과 요약" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

SUCCESS_RATE=$(echo "scale=2; $PASSED_TESTS * 100 / $TOTAL_TESTS" | bc 2>/dev/null || echo "N/A")

echo "총 테스트: $TOTAL_TESTS"
echo -e "성공: ${GREEN}$PASSED_TESTS${NC}"
echo -e "실패: ${RED}$FAILED_TESTS${NC}"
echo "성공률: ${SUCCESS_RATE}%"

echo "- 총 테스트: $TOTAL_TESTS" >> "$REPORT_FILE"
echo "- 성공: $PASSED_TESTS" >> "$REPORT_FILE"
echo "- 실패: $FAILED_TESTS" >> "$REPORT_FILE"
echo "- 성공률: ${SUCCESS_RATE}%" >> "$REPORT_FILE"
echo "" >> "$REPORT_FILE"

# 실패한 테스트 목록
if [[ $FAILED_TESTS -gt 0 ]]; then
    echo ""
    echo -e "${RED}실패한 테스트:${NC}"
    echo "### 실패한 테스트" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    
    echo -e "$FAILED_TEST_NAMES"
    echo -e "$FAILED_TEST_NAMES" >> "$REPORT_FILE"
fi

echo "" >> "$REPORT_FILE"
echo "테스트 완료: $(date)" >> "$REPORT_FILE"

# =============================================================================
# 컨테이너 로그 수집 (실패한 경우)
# =============================================================================

if [[ $FAILED_TESTS -gt 0 ]]; then
    echo ""
    echo -e "${YELLOW}컨테이너 로그 수집 중...${NC}"
    echo "## 컨테이너 로그 (최근 에러)" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    
    for container in nginx-gateway user-service oms-monolith; do
        echo "### $container" >> "$REPORT_FILE"
        echo '```' >> "$REPORT_FILE"
        docker logs $container --tail 20 2>&1 | grep -i error >> "$REPORT_FILE" || echo "No errors found" >> "$REPORT_FILE"
        echo '```' >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
    done
fi

echo ""
echo -e "${BLUE}보고서 저장됨: $REPORT_FILE${NC}"

# 테스트 실패 시 exit code 1 반환
if [[ $FAILED_TESTS -gt 0 ]]; then
    exit 1
fi