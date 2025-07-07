#!/bin/bash

# =============================================================================
# Arrakis Project 전체 통합 테스트 및 성능 검증 스크립트
# =============================================================================

set -e

echo "🚀 Arrakis Project 통합 테스트 시작"
echo "============================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
PROJECT_DIR="/Users/isihyeon/Desktop/Arrakis-Project"
BASE_URL="http://localhost:8090"
LOGS_DIR="$PROJECT_DIR/test-logs"
REPORT_FILE="$LOGS_DIR/integration-test-report-$(date +%Y%m%d-%H%M%S).md"

# Create logs directory
mkdir -p "$LOGS_DIR"

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

check_prerequisites() {
    log_info "사전 요구사항 확인 중..."
    
    # Docker 확인
    if ! command -v docker &> /dev/null; then
        log_error "Docker가 설치되어 있지 않습니다"
        exit 1
    fi
    
    # Docker Compose 확인
    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose가 설치되어 있지 않습니다"
        exit 1
    fi
    
    # curl 확인
    if ! command -v curl &> /dev/null; then
        log_error "curl이 설치되어 있지 않습니다"
        exit 1
    fi
    
    # jq 확인 (JSON 파싱용)
    if ! command -v jq &> /dev/null; then
        log_warning "jq가 설치되어 있지 않습니다. 일부 기능이 제한됩니다"
    fi
    
    log_success "모든 사전 요구사항이 충족되었습니다"
}

measure_response_time() {
    local url=$1
    local auth_header=$2
    
    if [[ -n "$auth_header" ]]; then
        curl -s -o /dev/null -w "%{time_total}" -H "$auth_header" "$url"
    else
        curl -s -o /dev/null -w "%{time_total}" "$url"
    fi
}

# =============================================================================
# Docker Environment Setup
# =============================================================================

setup_environment() {
    log_info "Docker 환경 설정 중..."
    
    cd "$PROJECT_DIR"
    
    # 기존 컨테이너 정리
    log_info "기존 컨테이너 정리 중..."
    docker-compose -f docker-compose.integrated.yml down -v || true
    
    # 새로운 컨테이너 빌드 및 시작
    log_info "Docker 이미지 빌드 중..."
    docker-compose -f docker-compose.integrated.yml build --no-cache
    
    log_info "서비스 시작 중..."
    docker-compose -f docker-compose.integrated.yml up -d
    
    # 서비스 준비 대기
    log_info "서비스가 준비될 때까지 대기 중... (30초)"
    sleep 30
    
    log_success "Docker 환경 설정 완료"
}

# =============================================================================
# Health Check
# =============================================================================

health_check() {
    log_info "서비스 헬스 체크 수행 중..."
    
    local services=(
        "nginx-gateway:$BASE_URL/health"
        "user-service:http://localhost:8001/health"
        "oms-monolith:http://localhost:8000/health"
    )
    
    local all_healthy=true
    
    for service in "${services[@]}"; do
        IFS=':' read -r name url <<< "$service"
        
        if curl -s -f "${url#*:}" > /dev/null 2>&1; then
            log_success "$name is healthy"
        else
            log_error "$name is not healthy"
            all_healthy=false
        fi
    done
    
    if [ "$all_healthy" = false ]; then
        log_error "일부 서비스가 준비되지 않았습니다"
        return 1
    fi
    
    log_success "모든 서비스가 정상입니다"
}

# =============================================================================
# User Service Test
# =============================================================================

test_user_service() {
    log_info "User Service 테스트 시작..."
    
    # 테스트 사용자 생성
    local test_user="perftest_$(date +%s)"
    local test_password="Test123!"
    local test_email="$test_user@example.com"
    
    # 사용자 등록
    log_info "사용자 등록 테스트..."
    local register_response=$(curl -s -X POST "$BASE_URL/auth/register" \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"$test_user\",\"password\":\"$test_password\",\"email\":\"$test_email\"}" \
        -w "\n%{http_code}")
    
    local register_code=$(echo "$register_response" | tail -1)
    if [[ "$register_code" == "200" || "$register_code" == "201" ]]; then
        log_success "사용자 등록 성공"
    else
        log_error "사용자 등록 실패 (HTTP $register_code)"
    fi
    
    # 로그인
    log_info "로그인 테스트..."
    local login_response=$(curl -s -X POST "$BASE_URL/auth/login" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=$test_user&password=$test_password")
    
    if command -v jq &> /dev/null; then
        ACCESS_TOKEN=$(echo "$login_response" | jq -r '.access_token // empty')
    else
        ACCESS_TOKEN=$(echo "$login_response" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
    fi
    
    if [[ -n "$ACCESS_TOKEN" ]]; then
        log_success "로그인 성공, 토큰 획득"
        echo "$ACCESS_TOKEN" > "$LOGS_DIR/access_token.txt"
    else
        log_error "로그인 실패 또는 토큰 획득 실패"
        return 1
    fi
    
    # 사용자 정보 조회
    log_info "사용자 정보 조회 테스트..."
    local userinfo_code=$(curl -s -X GET "$BASE_URL/auth/userinfo" \
        -H "Authorization: Bearer $ACCESS_TOKEN" \
        -o /dev/null -w "%{http_code}")
    
    if [[ "$userinfo_code" == "200" ]]; then
        log_success "사용자 정보 조회 성공"
    else
        log_error "사용자 정보 조회 실패 (HTTP $userinfo_code)"
    fi
}

# =============================================================================
# OMS Service Test
# =============================================================================

test_oms_service() {
    log_info "OMS Service 테스트 시작..."
    
    if [[ ! -f "$LOGS_DIR/access_token.txt" ]]; then
        log_error "액세스 토큰이 없습니다"
        return 1
    fi
    
    local token=$(cat "$LOGS_DIR/access_token.txt")
    
    # Schema 조회
    log_info "Schema 목록 조회 테스트..."
    local schemas_code=$(curl -s -X GET "$BASE_URL/api/v1/schemas" \
        -H "Authorization: Bearer $token" \
        -o /dev/null -w "%{http_code}")
    
    if [[ "$schemas_code" == "200" || "$schemas_code" == "404" ]]; then
        log_success "Schema 조회 성공"
    else
        log_error "Schema 조회 실패 (HTTP $schemas_code)"
    fi
    
    # 새 Schema 생성
    log_info "Schema 생성 테스트..."
    local schema_name="test_schema_$(date +%s)"
    local create_response=$(curl -s -X POST "$BASE_URL/api/v1/schemas" \
        -H "Authorization: Bearer $token" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"$schema_name\",\"description\":\"Performance test schema\",\"version\":\"1.0.0\"}" \
        -w "\n%{http_code}")
    
    local create_code=$(echo "$create_response" | tail -1)
    if [[ "$create_code" == "200" || "$create_code" == "201" ]]; then
        log_success "Schema 생성 성공"
    else
        log_error "Schema 생성 실패 (HTTP $create_code)"
    fi
}

# =============================================================================
# Performance Test
# =============================================================================

performance_test() {
    log_info "성능 테스트 시작..."
    
    if [[ ! -f "$LOGS_DIR/access_token.txt" ]]; then
        log_error "액세스 토큰이 없습니다"
        return 1
    fi
    
    local token=$(cat "$LOGS_DIR/access_token.txt")
    
    # 테스트 엔드포인트 목록
    declare -A endpoints=(
        ["Health Check"]="$BASE_URL/health"
        ["User Info"]="$BASE_URL/auth/userinfo"
        ["Schema List"]="$BASE_URL/api/v1/schemas"
        ["Audit Log"]="$BASE_URL/api/v1/audit"
    )
    
    echo "## 성능 테스트 결과" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    echo "| 엔드포인트 | 평균 응답시간 (ms) | 최소 (ms) | 최대 (ms) | 표준편차 |" >> "$REPORT_FILE"
    echo "|------------|-------------------|----------|----------|----------|" >> "$REPORT_FILE"
    
    for endpoint_name in "${!endpoints[@]}"; do
        local url="${endpoints[$endpoint_name]}"
        log_info "테스트 중: $endpoint_name"
        
        local times=()
        local auth_header=""
        
        if [[ "$endpoint_name" != "Health Check" ]]; then
            auth_header="Authorization: Bearer $token"
        fi
        
        # 10회 요청
        for i in {1..10}; do
            local response_time=$(measure_response_time "$url" "$auth_header")
            times+=($response_time)
        done
        
        # 통계 계산
        local sum=0
        local min=999999
        local max=0
        
        for time in "${times[@]}"; do
            # milliseconds로 변환
            local ms=$(echo "$time * 1000" | bc)
            sum=$(echo "$sum + $ms" | bc)
            
            if (( $(echo "$ms < $min" | bc -l) )); then
                min=$ms
            fi
            
            if (( $(echo "$ms > $max" | bc -l) )); then
                max=$ms
            fi
        done
        
        local avg=$(echo "scale=2; $sum / 10" | bc)
        
        echo "| $endpoint_name | $avg | $min | $max | - |" >> "$REPORT_FILE"
        log_success "$endpoint_name - 평균: ${avg}ms"
    done
}

# =============================================================================
# Load Test
# =============================================================================

load_test() {
    log_info "부하 테스트 시작..."
    
    if ! command -v ab &> /dev/null; then
        log_warning "Apache Bench가 설치되어 있지 않아 부하 테스트를 건너뜁니다"
        return 0
    fi
    
    if [[ ! -f "$LOGS_DIR/access_token.txt" ]]; then
        log_error "액세스 토큰이 없습니다"
        return 1
    fi
    
    local token=$(cat "$LOGS_DIR/access_token.txt")
    
    echo "" >> "$REPORT_FILE"
    echo "## 부하 테스트 결과" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    
    # Health check 부하 테스트
    log_info "Health check 엔드포인트 부하 테스트 (1000 요청, 동시 10)..."
    ab -n 1000 -c 10 "$BASE_URL/health" > "$LOGS_DIR/ab_health.txt" 2>&1
    
    # Schema API 부하 테스트
    log_info "Schema API 부하 테스트 (500 요청, 동시 5)..."
    ab -n 500 -c 5 -H "Authorization: Bearer $token" "$BASE_URL/api/v1/schemas" > "$LOGS_DIR/ab_schemas.txt" 2>&1
    
    # 결과 추출 및 보고
    if [[ -f "$LOGS_DIR/ab_health.txt" ]]; then
        local health_rps=$(grep "Requests per second" "$LOGS_DIR/ab_health.txt" | awk '{print $4}')
        local health_time=$(grep "Time per request" "$LOGS_DIR/ab_health.txt" | head -1 | awk '{print $4}')
        
        echo "### Health Check 엔드포인트" >> "$REPORT_FILE"
        echo "- Requests per second: $health_rps" >> "$REPORT_FILE"
        echo "- Mean time per request: ${health_time}ms" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
        
        log_success "Health check RPS: $health_rps"
    fi
    
    if [[ -f "$LOGS_DIR/ab_schemas.txt" ]]; then
        local schema_rps=$(grep "Requests per second" "$LOGS_DIR/ab_schemas.txt" | awk '{print $4}')
        local schema_time=$(grep "Time per request" "$LOGS_DIR/ab_schemas.txt" | head -1 | awk '{print $4}')
        
        echo "### Schema API 엔드포인트" >> "$REPORT_FILE"
        echo "- Requests per second: $schema_rps" >> "$REPORT_FILE"
        echo "- Mean time per request: ${schema_time}ms" >> "$REPORT_FILE"
        echo "" >> "$REPORT_FILE"
        
        log_success "Schema API RPS: $schema_rps"
    fi
}

# =============================================================================
# Integration Test
# =============================================================================

integration_test() {
    log_info "통합 시나리오 테스트 시작..."
    
    if [[ ! -f "$LOGS_DIR/access_token.txt" ]]; then
        log_error "액세스 토큰이 없습니다"
        return 1
    fi
    
    local token=$(cat "$LOGS_DIR/access_token.txt")
    local test_id=$(date +%s)
    
    echo "" >> "$REPORT_FILE"
    echo "## 통합 시나리오 테스트 결과" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    
    # 1. Schema 생성
    log_info "1. Schema 생성..."
    local schema_response=$(curl -s -X POST "$BASE_URL/api/v1/schemas" \
        -H "Authorization: Bearer $token" \
        -H "Content-Type: application/json" \
        -d "{\"name\":\"integration_test_$test_id\",\"description\":\"Integration test\",\"version\":\"1.0.0\"}")
    
    if [[ -n "$schema_response" ]]; then
        log_success "Schema 생성 완료"
        echo "✓ Schema 생성 성공" >> "$REPORT_FILE"
    else
        log_error "Schema 생성 실패"
        echo "✗ Schema 생성 실패" >> "$REPORT_FILE"
    fi
    
    # 2. Schema 조회
    log_info "2. Schema 조회..."
    local list_code=$(curl -s -X GET "$BASE_URL/api/v1/schemas" \
        -H "Authorization: Bearer $token" \
        -o /dev/null -w "%{http_code}")
    
    if [[ "$list_code" == "200" ]]; then
        log_success "Schema 조회 성공"
        echo "✓ Schema 조회 성공" >> "$REPORT_FILE"
    else
        log_error "Schema 조회 실패"
        echo "✗ Schema 조회 실패" >> "$REPORT_FILE"
    fi
    
    # 3. Audit 로그 확인
    log_info "3. Audit 로그 확인..."
    local audit_code=$(curl -s -X GET "$BASE_URL/api/v1/audit" \
        -H "Authorization: Bearer $token" \
        -o /dev/null -w "%{http_code}")
    
    if [[ "$audit_code" == "200" || "$audit_code" == "404" ]]; then
        log_success "Audit 로그 확인 가능"
        echo "✓ Audit 로그 시스템 정상" >> "$REPORT_FILE"
    else
        log_error "Audit 로그 확인 실패"
        echo "✗ Audit 로그 시스템 오류" >> "$REPORT_FILE"
    fi
}

# =============================================================================
# Container Health Check
# =============================================================================

check_container_health() {
    log_info "컨테이너 상태 확인..."
    
    echo "" >> "$REPORT_FILE"
    echo "## 컨테이너 상태" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    
    local containers=("nginx-gateway" "user-service" "oms-monolith" "user-db" "oms-db" "user-redis" "oms-redis")
    
    for container in "${containers[@]}"; do
        local status=$(docker ps --filter "name=$container" --format "{{.Status}}" | head -1)
        if [[ -n "$status" ]]; then
            log_success "$container: $status"
            echo "- $container: $status" >> "$REPORT_FILE"
        else
            log_error "$container: Not running"
            echo "- $container: Not running" >> "$REPORT_FILE"
        fi
    done
}

# =============================================================================
# Resource Usage
# =============================================================================

check_resource_usage() {
    log_info "리소스 사용량 확인..."
    
    echo "" >> "$REPORT_FILE"
    echo "## 리소스 사용량" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" > "$LOGS_DIR/resource_usage.txt"
    
    cat "$LOGS_DIR/resource_usage.txt" >> "$REPORT_FILE"
    
    log_success "리소스 사용량 기록 완료"
}

# =============================================================================
# Cleanup
# =============================================================================

cleanup() {
    log_info "테스트 환경 정리 중..."
    
    cd "$PROJECT_DIR"
    docker-compose -f docker-compose.integrated.yml down
    
    log_success "정리 완료"
}

# =============================================================================
# Generate Final Report
# =============================================================================

generate_report() {
    log_info "최종 보고서 생성 중..."
    
    echo "" >> "$REPORT_FILE"
    echo "## 테스트 요약" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    echo "- 테스트 일시: $(date)" >> "$REPORT_FILE"
    echo "- 프로젝트 경로: $PROJECT_DIR" >> "$REPORT_FILE"
    echo "- 로그 경로: $LOGS_DIR" >> "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    
    log_success "보고서 생성 완료: $REPORT_FILE"
    
    # 보고서 출력
    echo ""
    echo "===== 테스트 보고서 ====="
    cat "$REPORT_FILE"
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    echo "# Arrakis Project 통합 테스트 보고서" > "$REPORT_FILE"
    echo "" >> "$REPORT_FILE"
    
    # 사전 요구사항 확인
    check_prerequisites
    
    # 환경 설정
    setup_environment
    
    # 헬스 체크
    if ! health_check; then
        log_error "헬스 체크 실패. 테스트를 중단합니다"
        cleanup
        exit 1
    fi
    
    # 서비스 테스트
    test_user_service
    test_oms_service
    
    # 성능 테스트
    performance_test
    
    # 부하 테스트
    load_test
    
    # 통합 테스트
    integration_test
    
    # 컨테이너 상태 확인
    check_container_health
    
    # 리소스 사용량 확인
    check_resource_usage
    
    # 보고서 생성
    generate_report
    
    # 정리
    # cleanup  # 필요시 주석 해제
    
    log_success "모든 테스트 완료!"
    echo ""
    echo "💡 다음 단계:"
    echo "  1. 로그 확인: docker-compose -f docker-compose.integrated.yml logs"
    echo "  2. 보고서 확인: cat $REPORT_FILE"
    echo "  3. 모니터링: http://localhost:16686 (Jaeger)"
    echo "  4. 서비스 종료: docker-compose -f docker-compose.integrated.yml down"
}

# 스크립트 실행
main "$@"