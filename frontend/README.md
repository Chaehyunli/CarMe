# CarMe Frontend

Vue 3 + TypeScript + Vite 프런트엔드를 로컬 Node 환경에서 실행한다. API는 로컬에서 실행 중인 FastAPI(`http://localhost:8000`)를 사용한다.

## 사전 조건

- Node.js 22 이상
- npm
- backend가 `http://localhost:8000`에서 실행 중이어야 한다.

## 1. 환경 파일과 의존성

```bash
cd frontend
cp .env.example .env
npm install
```

`.env`의 기본값은 다음과 같다.

```dotenv
VITE_API_BASE_URL=http://localhost:8000
```

브라우저는 Ollama에 직접 접근하지 않는다. 인증과 운영 API는 FastAPI를 통한다. 관리자 PDF 업로드만 FastAPI가 발급한 5분짜리 private-storage PUT URL로 직접 전송하며, object key·bucket·장기 자격증명은 화면과 API 응답에 노출하지 않는다.

## 2. 개발 서버 실행

```bash
cd frontend
npm run dev
```

Vite가 표시한 주소(기본 `http://localhost:5173`)로 접속한다.

## 검사와 배포 빌드

```bash
cd frontend
npm run lint
npm run build
npm run preview
```

화면·상태 설계는 [와이어프레임](../docs/와이어프레임.md), API 계약은 [API 명세서](../docs/api_명세서.md)를 따른다.
