# Icon Blaster 🎨

AI로 한 번에 10개의 아이콘을 생성하고 비교할 수 있는 웹 애플리케이션입니다.

## 주요 기능

- **멀티 아이콘 생성**: 하나의 프롬프트로 10개의 다양한 아이콘 버전을 동시에 생성
- **실시간 비교**: 생성된 아이콘들을 그리드 형태로 한눈에 비교
- **좋아요 시스템**: 마음에 드는 아이콘에 좋아요 표시
- **다운로드 기능**: 개별 또는 일괄 다운로드 지원
- **에러 처리**: 실패한 생성에 대한 재시도 로직 및 사용자 피드백
- **반응형 디자인**: 모든 디바이스에서 최적화된 사용자 경험

## 기술 스택

- **Frontend**: Next.js 15, React, TypeScript
- **Styling**: Tailwind CSS, shadcn/ui
- **AI Integration**: OpenAI DALL-E 3
- **State Management**: React Hooks
- **Deployment**: Vercel

## 시작하기

### 1. 저장소 클론

```bash
git clone https://github.com/ludia8888/Icon-Blaster.git
cd Icon-Blaster
```

### 2. 의존성 설치

```bash
npm install
```

### 3. 환경 변수 설정

`.env.example` 파일을 `.env.local`로 복사하고 OpenAI API 키를 설정합니다:

```bash
cp .env.example .env.local
```

`.env.local` 파일을 열어 실제 API 키를 입력합니다:

```env
OPENAI_API_KEY=your_actual_openai_api_key_here
```

### 4. 개발 서버 실행

```bash
npm run dev
```

브라우저에서 [http://localhost:3000](http://localhost:3000)을 열어 애플리케이션을 확인합니다.

## OpenAI API 키 발급 방법

1. [OpenAI Platform](https://platform.openai.com/api-keys)에 로그인
2. "Create new secret key" 버튼 클릭
3. 생성된 API 키를 복사하여 `.env.local` 파일에 붙여넣기

## Vercel 배포

### 자동 배포 (추천)

1. GitHub 저장소를 Vercel에 연결
2. 환경 변수 설정:
   - `OPENAI_API_KEY`: OpenAI API 키

### 수동 배포

```bash
# Vercel CLI 설치
npm i -g vercel

# 배포
vercel

# 환경 변수 추가
vercel env add OPENAI_API_KEY
```

## 프로젝트 구조

```
src/
├── app/
│   ├── api/
│   │   └── generate-icons/
│   │       └── route.ts         # OpenAI API 연동
│   ├── globals.css              # 전역 스타일
│   ├── layout.tsx               # 레이아웃
│   └── page.tsx                 # 메인 페이지
├── components/
│   └── ui/                      # shadcn/ui 컴포넌트
├── lib/
│   ├── download.ts              # 다운로드 유틸리티
│   └── utils.ts                 # 공통 유틸리티
└── types/
    └── index.ts                 # TypeScript 타입 정의
```

## API 엔드포인트

### POST `/api/generate-icons`

프롬프트를 기반으로 10개의 아이콘을 생성합니다.

**Request:**
```json
{
  "prompt": "minimalist coffee icon"
}
```

**Response:**
```json
{
  "icons": [
    {
      "id": "icon-123456789-0",
      "imageUrl": "https://...",
      "liked": false
    }
  ],
  "successCount": 10,
  "totalAttempted": 10
}
```

## 기여하기

1. 저장소를 Fork 합니다
2. 기능 브랜치를 생성합니다 (`git checkout -b feature/AmazingFeature`)
3. 변경사항을 커밋합니다 (`git commit -m 'Add some AmazingFeature'`)
4. 브랜치에 푸시합니다 (`git push origin feature/AmazingFeature`)
5. Pull Request를 생성합니다

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 문의

프로젝트에 대한 문의나 제안이 있으시면 GitHub Issues를 통해 연락해주세요.
