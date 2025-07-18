# 🔥 THINK ULTRA!! Complex Types Testing Guide

## 개요

이 문서는 SPICE HARVESTER의 복합 타입(Complex Types) 시스템에 대한 종합적인 테스트 가이드입니다.

## 지원하는 복합 타입 (10개)

1. **ARRAY** - 배열 타입 (항목 타입, 크기 제한, 유니크 제약)
2. **OBJECT** - 중첩 객체 (스키마 검증, 필수 필드)
3. **ENUM** - 열거형 (허용된 값 목록)
4. **MONEY** - 통화 타입 (금액, 통화 코드, 소수점 자리수)
5. **PHONE** - 전화번호 (국제 형식, 지역 제한)
6. **EMAIL** - 이메일 주소 (도메인 제한, 배달 가능성 체크)
7. **COORDINATE** - GPS 좌표 (위도/경도, 정밀도, 경계 박스)
8. **ADDRESS** - 주소 (구조화된 주소, 국가별 검증)
9. **IMAGE** - 이미지 URL (확장자 검증, 도메인 화이트리스트)
10. **FILE** - 파일 첨부 (크기 제한, 확장자 제한)

## 테스트 파일 구조

```
backend/
├── shared/
│   ├── models/
│   │   └── common.py                    # DataType enum with complex types
│   ├── validators/
│   │   └── complex_type_validator.py    # 복합 타입 검증 로직
│   └── serializers/
│       └── complex_type_serializer.py   # 직렬화/역직렬화
│
├── test_complex_validator_ultra.py      # 단위 테스트
├── test_complex_types_terminus_integration.py  # TerminusDB 통합 테스트
├── test_complex_types_bff_integration.py      # BFF end-to-end 테스트
└── run_complex_types_tests.py          # 테스트 러너
```

## 테스트 실행 방법

### 1. 전체 테스트 실행

```bash
# 모든 테스트를 순차적으로 실행
python run_complex_types_tests.py
```

### 2. 개별 테스트 실행

```bash
# 단위 테스트만 실행
python test_complex_validator_ultra.py

# TerminusDB 통합 테스트만 실행
python test_complex_types_terminus_integration.py

# BFF 통합 테스트만 실행
python test_complex_types_bff_integration.py
```

### 3. 서비스 실행 필요

통합 테스트를 위해서는 다음 서비스들이 실행 중이어야 합니다:

```bash
# Terminal 1: OMS 서비스
cd backend/ontology-management-service
python main.py

# Terminal 2: BFF 서비스
cd backend/backend-for-frontend
python main.py

# Terminal 3: TerminusDB (Docker)
docker-compose up terminusdb
```

## 테스트 범위

### 1. ComplexTypeValidator 단위 테스트
- ✅ 모든 10개 복합 타입의 검증 로직
- ✅ 유효한 데이터와 무효한 데이터 테스트
- ✅ 제약조건(constraints) 검증
- ✅ 직렬화/역직렬화

### 2. TerminusDB 통합 테스트
- ✅ 복합 타입을 가진 온톨로지 생성
- ✅ 데이터베이스에 실제 스키마 저장
- ✅ 복합 타입 조합 테스트
- ✅ 전체 e-commerce 모델 생성

### 3. BFF 통합 테스트
- ✅ 레이블 매핑 (다국어 지원)
- ✅ API를 통한 복합 타입 생성
- ✅ 전체 워크플로우 검증
- ✅ 중첩된 복합 타입 구조

## 예제: E-commerce 상품 모델

```python
{
    "label": {
        "en": "E-commerce Product",
        "ko": "전자상거래 상품"
    },
    "properties": [
        {
            "name": "price",
            "type": "custom:money",
            "constraints": {
                "minAmount": 0,
                "maxAmount": 999999.99,
                "allowedCurrencies": ["USD", "EUR", "KRW"]
            }
        },
        {
            "name": "images",
            "type": "custom:array",
            "constraints": {
                "itemType": "custom:image",
                "maxItems": 20
            }
        },
        {
            "name": "vendor",
            "type": "custom:object",
            "constraints": {
                "schema": {
                    "email": {"type": "custom:email"},
                    "phone": {"type": "custom:phone"},
                    "address": {"type": "custom:address"}
                }
            }
        }
    ]
}
```

## 검증 예제

### MONEY 타입 검증
```python
# 유효한 값
"1234.56 USD"
{"amount": 1234.56, "currency": "USD"}

# 무효한 값
"1234.56 XYZ"  # 지원하지 않는 통화
"-100 USD"      # 음수 (min_amount=0인 경우)
```

### EMAIL 타입 검증
```python
# 제약조건
constraints = {
    "allowedDomains": ["company.com", "business.com"]
}

# 유효한 값
"user@company.com"

# 무효한 값
"user@gmail.com"  # 허용되지 않은 도메인
```

## 성공 기준

모든 테스트가 통과하면 다음을 보장합니다:

1. ✅ 10개 복합 타입 모두 정상 작동
2. ✅ TerminusDB에 복합 타입 스키마 저장 가능
3. ✅ BFF를 통한 다국어 레이블 지원
4. ✅ 복합 타입 중첩 및 조합 가능
5. ✅ 제약조건 검증 정상 작동

## 트러블슈팅

### 1. ModuleNotFoundError: phonenumbers
```bash
pip install phonenumbers email-validator --break-system-packages
```

### 2. Connection refused
- OMS와 BFF 서비스가 실행 중인지 확인
- TerminusDB Docker 컨테이너가 실행 중인지 확인

### 3. 테스트 실패
- 각 테스트의 상세 로그 확인
- JSON 결과 파일 확인: `complex_types_test_results_*.json`

## 다음 단계

1. 실제 문서(document) 생성 시 복합 타입 데이터 검증
2. GraphQL 스키마에 복합 타입 반영
3. UI 컴포넌트에서 복합 타입 입력 지원
4. 복합 타입 데이터 쿼리 및 필터링

## 🔥 THINK ULTRA!!

이제 SPICE HARVESTER는 단순한 문자열과 숫자를 넘어서, 실제 비즈니스에서 필요한 모든 복합 데이터 타입을 지원합니다!