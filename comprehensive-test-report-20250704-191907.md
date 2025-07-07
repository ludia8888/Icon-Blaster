# Arrakis Project 포괄적 테스트 보고서

테스트 시작: Fri Jul  4 19:19:08 KST 2025

## 1. 서비스 가용성 테스트

## 2. 인증 테스트

## 3. API 엔드포인트 테스트

## 4. 데이터 무결성 테스트

## 5. 성능 및 부하 테스트

## 6. 에러 처리 테스트

## 7. 서비스 간 통합 테스트

## 8. 장애 복구 테스트

## 테스트 결과 요약

- 총 테스트: 19
- 성공: 12
- 실패: 7
- 성공률: 63.15%

### 실패한 테스트

User Service Direct Health: FAIL
TerminusDB Health: FAIL
동일 토큰으로 일관된 응답: FAIL
동시 50개 요청 처리: FAIL
Health check 응답 시간 < 100ms: FAIL
JWT issuer가 'user-service': FAIL
JWT audience가 'oms': FAIL


테스트 완료: Fri Jul  4 19:19:15 KST 2025
## 컨테이너 로그 (최근 에러)

### nginx-gateway
```
No errors found
```

### user-service
```
{"asctime": "2025-07-04 10:13:24", "name": "passlib.handlers.bcrypt", "levelname": "WARNING", "message": "(trapped) error reading bcrypt version", "exc_info": "Traceback (most recent call last):\n  File \"/usr/local/lib/python3.11/site-packages/passlib/handlers/bcrypt.py\", line 620, in _load_backend_mixin\n    version = _bcrypt.__about__.__version__\n              ^^^^^^^^^^^^^^^^^\nAttributeError: module 'bcrypt' has no attribute '__about__'"}
```

### oms-monolith
```
TypeError: SimpleTerminusDBClient.__init__() got an unexpected keyword argument 'endpoint'
```

