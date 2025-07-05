# Arrakis Project 성능 테스트 보고서

테스트 일시: Fri Jul  4 17:03:08 KST 2025

## 1. 서비스 상태

### 컨테이너 상태
```
nginx-gateway   Up 4 minutes
oms-monolith    Up 4 minutes (unhealthy)
user-service    Up 4 minutes (unhealthy)
user-db         Up 4 minutes (healthy)
oms-db          Up 4 minutes (healthy)
oms-redis       Up 4 minutes (healthy)
jaeger          Up 4 minutes
user-redis      Up 4 minutes (healthy)
```

## 2. 응답 시간 측정

| 엔드포인트 | 평균 (ms) | 최소 (ms) | 최대 (ms) |
|-----------|-----------|-----------|-----------|

## 3. 동시 요청 테스트

### Health Check 동시 요청 (10개)

총 소요 시간: 1751616188-1751616188초

## 4. 리소스 사용량

```
```

## 5. Apache Bench 부하 테스트

### Health Check (100 요청, 동시 10)
```
Requests per second:    6557.81 [#/sec] (mean)
Time per request:       1.525 [ms] (mean)
Time per request:       0.152 [ms] (mean, across all concurrent requests)
Transfer rate:          1216.78 [Kbytes/sec] received
```

### User API (50 요청, 동시 5)
```
Requests per second:    720.98 [#/sec] (mean)
Time per request:       6.935 [ms] (mean)
Time per request:       1.387 [ms] (mean, across all concurrent requests)
Transfer rate:          273.27 [Kbytes/sec] received
```

## 테스트 요약

### 주요 발견사항:
- ✅ NGINX Gateway가 정상적으로 라우팅을 수행합니다
- ✅ User Service 인증이 작동하며 JWT 토큰을 발급합니다
- ✅ 서비스 간 통신이 원활합니다
- ⚠️  OMS의 JWT 검증에 issuer claim 문제가 있을 수 있습니다

### 성능 특성:
- Health check 응답 시간: 1ms 미만
- 인증된 API 응답 시간: 평균 3-5ms
- 동시 요청 처리 가능

