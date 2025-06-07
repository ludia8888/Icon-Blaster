[CICDSpec.md]

## **CICDSpec.md**

### **1. 문서 개요**

이 문서는 Ontology Editor 플랫폼의 CI/CD(Continuous Integration & Continuous Deployment) 파이프라인을 엔터프라이즈 프로덕션 수준으로 정의합니다. Git 브랜치 전략, 코드 품질 검사, 빌드 및 배포 워크플로우, 환경별 승인 프로세스, 롤백 메커니즘, 보안 스캔, 모니터링 알림, 비상 대응 등 전체 릴리스 라이프사이클을 상세히 규격화하여, DevOps 팀이 문서만으로 완전 자동화된 배포 시스템을 구축·운영할 수 있도록 가이드합니다.

**대상 독자:** DevOps 엔지니어, SRE, 플랫폼 인프라 팀

---

### **2. Git 브랜치 전략**

```
main              • 프로덕션 릴리즈 (태그 v1.x.x)
develop           • 통합 브랜치 (스테이징 자동 배포)
feature/{ticket}  • 신규 기능 개발 (PR → develop 머지)
release/{version} • 릴리스 QA 준비 (PR → main 머지, 태그)
hotfix/{issue}    • 긴급 수정 (PR → main → 태그 → develop 머지)
```

- **Pull Request 정책**
  - 메시지: type(scope): subject (feat, fix, docs, chore 등)
  - 최소 2명 리뷰·승인, CI 통과 필수
  - 브랜치 보호: force-push 금지, fast-forward 병합만 허용

---

### **3. 워크플로우 정의 (.github/workflows/ci-cd.yml)**

```
name: Ontology Editor CI/CD
on:
  push:
    branches:
      - develop
      - main
      - 'release/**'
      - 'feature/**'
  pull_request:
    branches:
      - develop
      - main

jobs:
  # 1. 코드 품질 검사 및 테스트
  lint-test:
    runs-on: ubuntu-latest
    services:
      postgres: { image: postgres:13, env: {...}, ports: ['5432:5432'], options: '...'}
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with: { node-version: '18' }
      - name: Lint & TypeCheck
        run: |
          cd frontend && npm ci && npm run lint && npm run type
          cd ../server && npm ci && npm run lint && npm run type
      - name: Unit & Integration Tests
        run: |
          cd frontend && npm run test:unit -- --coverage
          cd ../server && npm run test:integration
      - name: Security Scans
        run: |
          npm run scan:container
          npm run snyk:scan

  # 2. 이미지 빌드 및 스캔
  build-push:
    needs: lint-test
    runs-on: ubuntu-latest
    environment: ${{ github.ref == 'refs/heads/main' && 'production' || 'staging' }}
    permissions: write-all
    steps:
      - uses: actions/checkout@v3
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      - name: Login to Registry
        uses: docker/login-action@v2
        with: { registry: ${{ secrets.REGISTRY_URL }}, username: ${{ secrets.REGISTRY_USER }}, password: ${{ secrets.REGISTRY_TOKEN }} }
      - name: Build Multi-Arch Images
        run: |
          docker buildx build --platform linux/amd64,linux/arm64 \
            --tag ${{ secrets.REGISTRY_URL }}/onto-frontend:${{ github.sha }} \
            --tag ${{ secrets.REGISTRY_URL }}/onto-backend:${{ github.sha }} \
            --push .
      - name: Container Vulnerability Scan
        uses: aquasecurity/trivy-action@v0.4.14
        with: { image-ref: ${{ secrets.REGISTRY_URL }}/onto-frontend:${{ github.sha }} }

  # 3. 배포 및 릴리스
  deploy:
    needs: build-push
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Configure Kubectl
        run: |
          echo ${{ secrets.KUBE_CONFIG }} | base64 -d > kubeconfig
          export KUBECONFIG=$PWD/kubeconfig
      - name: Helm Diff
        run: |
          helm upgrade --install ontology-editor infra/k8s/ontology-editor \
            --values infra/k8s/ontology-editor/values-${{ github.ref == 'refs/heads/main' && 'prod' || 'staging' }}.yaml \
            --set image.tag=${{ github.sha }} --dry-run --debug
      - name: Helm Deploy
        run: |
          helm upgrade --install ontology-editor infra/k8s/ontology-editor \
            --values infra/k8s/ontology-editor/values-${{ github.ref == 'refs/heads/main' && 'prod' || 'staging' }}.yaml \
            --set image.tag=${{ github.sha }}
      - name: Verify Rollout
        run: |
          kubectl rollout status deployment/onto-backend -n ontology-editor
          kubectl rollout status deployment/onto-frontend -n ontology-editor

  # 4. Promotion Manual Approval
  promote:
    needs: deploy
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/develop'
    environment:
      name: production
      url: https://onto.company.com
    steps:
      - name: Await Approval
        uses: peter-evans/slash-command-dispatch@v2
        with: { reaction-token: ${{ secrets.GITHUB_TOKEN }}, issue-type: 'pull-request', commands: 'approve-deploy' }
      - name: Trigger Production Deploy
        run: gh workflow run ci-cd.yml -f ref=main
```

---

### **4. 프로모션 & 롤백 전략**

- **자동 스테이징 프로모션**: develop 푸시 시 스테이징에 자동 배포 후 Smoke Tests 실행
- **수동 프로덕션 승격**: /approve-deploy 커맨드 또는 GitHub 환경 보호 승인
- **프로덕션 롤백**: helm rollback ontology-editor <revision> 또는 kubectl rollout undo

---

### **5. 검증 단계**

1. **Static Analysis**: ESLint, Stylelint, TS Type-Check
2. **Unit Tests**: 목표 90% 커버리지
3. **Integration Tests**: Supertest with Testcontainers
4. **E2E Tests**: Cypress (core flows + accessibility)
5. **Security Scans**: Snyk, Trivy, OWASP ZAP Action
6. **Contract Tests**: Pact 브로커 연동

---

### **6. 모니터링 & 알림**

- **GitHub Actions**: Slack Notify Action (#ci-cd-alerts)
- **Prometheus Alertmanager**: 성공/실패, 배포 지연, 헬스체크 실패 → PagerDuty
- **Log Alerts**: Sentry Issue Alert, ElasticSearch 알람

---

### **7. 비상 대응**

- **빌드 실패**: PR 코멘트 + Slack 알림
- **배포 실패**: 즉각 롤백 + PagerDuty 알림
- **테스트 커버리지 감소**: 강제 PR 금지, 자동 라벨링

---

### **8. 운영 문서 & 가이드**

- **Runbook**: Jenkins → GitHub → ArgoCD 플로우 도해
- **Oncall Handbook**: Slack 알림 처리, 롤백 절차, DB 마이그레이션 핸들링

---

### **9. 후속 문서**

[QASpec.md]
[InfraSpec.md]
[BackendSpec.md]
