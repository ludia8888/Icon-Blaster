[InfraSpec.md]
## **InfraSpec.md**

### **1. 문서 개요**

이 문서는 Ontology Editor 플랫폼을 위한 인프라 및 배포 사양을 엔터프라이즈 프로덕션 수준으로 심층 규격화합니다. 컨테이너 이미지 관리, Kubernetes 구성(네임스페이스, 네트워크 정책, 리소스 설정), Helm 차트 및 Terraform IaC, CI/CD 파이프라인, 관측성, 보안, 백업·복구, 재해 복구 전략까지 포괄하여, DevOps 팀과 인프라 엔지니어가 문서만으로 완전 구축할 수 있도록 설계되었습니다.

**대상 독자:** DevOps 엔지니어, 인프라 아키텍트, SRE, 보안 팀

---

### **2. 컨테이너화 (Containerization)**

### **2.1 멀티 아키텍처 지원**

- docker buildx 사용하여 linux/amd64, linux/arm64 이미지 빌드
- 플랫폼 태그 예시: onto-frontend:latest-amd64, onto-frontend:latest-arm64

### **2.2 Dockerfile 베스트 프랙티스**

- **Frontend Dockerfile**
    - Stage 1: Node.js 빌드
        - npm ci --production=false + 캐시 활용(package-lock.json 변경 시만 재설치)
        - npm run build
    - Stage 2: Nginx Serve
        - nginx:stable-alpine 기반, /etc/nginx/conf.d/default.conf에 HTTP2, gzip, client_max_body_size 설정
        - 보안 헤더(CSP, HSTS) 추가
- **Backend Dockerfile**
    - Stage 1: Node.js 빌드 + 의존성 설치
    - Stage 2: slim Node.js 이미지(node:18-slim)로 실행
        - 비루트 유저(node) 사용
        - dist 폴더만 복사하여 최소 이미지

### **2.3 이미지 관리**

- 레지스트리: AWS ECR / GCP Artifact Registry
- 네이밍 컨벤션: <service>-<environment>:<git-sha>
- 스캔: Trivy GitHub Action으로 취약점 검사, Snyk 연동

---

### **3. IaC 및 배포 구성 (Kubernetes + Terraform + Helm)**

### **3.1 Terraform**

- **Modules**: network, kubernetes, ecr, rds, elasticache, opentelemetry
- **State**: S3 버킷 + DynamoDB 락
- **Environments**: dev, staging, prod 워크스페이스 분리

### **3.2 Helm 차트**

- **차트 구조**:

```
infra/k8s/ontology-editor/
├─ Chart.yaml
├─ values.yaml
├─ values-dev.yaml
├─ values-staging.yaml
├─ values-prod.yaml
├─ templates/
   ├─ namespace.yaml
   ├─ deployment-frontend.yaml
   ├─ deployment-backend.yaml
   ├─ service.yaml
   ├─ ingress.yaml
   ├─ configmap.yaml
   ├─ secret.yaml
   ├─ hpa.yaml
   ├─ networkpolicy.yaml
   └─ serviceaccount.yaml
```

- 
- **Values**:
    - 리소스 요청/제한(메모리/CPU)
    - 인그레스 호스트(onto.company.com)
    - TLS 비밀(cert-manager secret)
    - HPA 설정(Burst 용량 기반)

### **3.3 Kubernetes 리소스**

- **Namespace**: ontology-editor (레이블: env=...)
- **NetworkPolicy**: 서비스별 인바운드/아웃바운드 제어 (기본 Deny)
- **ServiceAccount & RBAC**: 최소 권한 원칙, Pod 별 서비스 계정
- **ConfigMap / Secret**: config와 민감 정보 분리, sealed-secrets 또는 Vault 통합
- **Ingress**: Nginx Ingress Controller + cert-manager Let’s Encrypt 자동 인증
- **HorizontalPodAutoscaler**: CPU 60% 기준, minReplicas:2, maxReplicas:10
- **PodDisruptionBudget**: maxUnavailable: 1
- **ResourceQuota**: 네임스페이스별 사용 제한 설정

---

### **4. CI/CD 파이프라인 (GitHub Actions + ArgoCD)**

### **4.1 GitOps 스타일 배포**

- **ArgoCD** 연동: Helm 차트 자동 동기화, Webhook으로 이미지 태그 업데이트 트리거

### **4.2 GitHub Actions**

- **Workflow**: .github/workflows/ci-cd.yaml
    1. **Lint & Test**: 프론트엔드 · 백엔드 검증
    2. **Build & Push**: Docker Buildx · ECR Push · 이미지 태그 매핑
    3. **Helm Diff & Release**: helm diff upgrade → helm upgrade --install
    4. **Promote**: dev → staging → prod 승인 플로우 (GitHub 환경 보호 정책)

---

### **5. 관측성 & 로깅**

### **5.1 Metrics**

- **Prometheus**: app_http_requests_total, app_http_request_duration_seconds, kafka_consumer_lag
- **ServiceMonitor**: kube-prometheus-stack CRD 적용
- **Grafana Dashboard**: API latency, error rate, pod CPU/메모리, HPA metrics, Kafka lag

### **5.2 로그**

- **Fluent Bit**: Node/Container 로그 수집 → Elasticsearch
- **Centralized Logging**: Kibana 대시보드
- **Structured Logs**: JSON 포맷, timestamp, level, service, requestId, userId, message
- **Sentry**: Exception 및 비정상 종료 알림

---

### **6. 보안 및 컴플라이언스**

### **6.1 네트워크**

- **VPC**: Private 서브넷에 DB, 캐시 위치, Public 서브넷에 ALB
- **Security Groups**: 최소 권한, 포트 제한 (DB 5432, ES 9200)
- **NetworkPolicy**: Pod 간 트래픽 제한

### **6.2 인증 & 비밀**

- **TLS**: Ingress 레벨에서 HTTPS 강제, HSTS
- **Secret 관리**: AWS KMS 암호화된 S3/Vault, sealed-secrets
- **IAM Role**: IRSA(AKS용 Pod Identity) / IAM Service Account

### **6.3 취약점 스캔**

- **Image Scanning**: Trivy CI 단계
- **CSP**: Nginx config에 CSP 헤더 적용
- **WAF**: AWS WAF 또는 Cloud Armor 룰 적용

---

### **7. 백업 & 재해 복구**

### **7.1 백업**

- **PostgreSQL**: pgBackRest으로 일일 Full + 아카이브 백업 → S3
- **ElasticSearch**: Snapshot API → S3, 주 단위 테스트 복원
- **Neo4j**: Enterprise Hot Backup → NFS

### **7.2 재해 복구**

- **RTO/RPO 목표**: RTO ≤ 15분, RPO ≤ 1시간
- **Cross-Region DR**: Terraform으로 DR 리전 프로비저닝, ECR 리플리케이션
- **Failover Runbook**: 자동화 스크립트 + 수동 지침 포함

---

### **8. 운영 절차 & 알람**

### **8.1 알람**

- **Prometheus Alertmanager**: API 5xx > 1%, DB 연결 실패, Index lag >30초 → Slack/PagerDuty
- **Health Checks**: Readiness & Liveness probes, Dashboard email 요약

### **8.2 운영**

- **Runbooks**: 버전 관리, 롤백, 긴급 패치 절차
- **Maintenance Window**: 주말 비업무시간 사전 공지
- **Capacity Planning**: 분기별 부하 테스트 및 리소스 조정

---

### **9. 비용 최적화**

- **Cluster Autoscaling**: KEDA 또는 Cluster-Autoscaler 설정
- **Spot Instances**: 비핵심 워커 노드용
- **Reserved Instances**: RDS, ElasticCache 장기 예약

---

### **10. 후속 문서 링크**

[CICDSpec.md]
[QASpec.md]
[BackendSpec.md]
[FrontendSpec.md]

