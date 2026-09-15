# CarMe Backend

FastAPI API와 LangChain RAG 모듈을 로컬 Python 환경에서 실행한다. Docker Compose는 PostgreSQL, MinIO, Ollama 같은 의존 서비스만 실행한다.

## 사전 조건

- Python 3.12 이상
- Docker Desktop

## 1. 의존 서비스 실행

저장소 루트에서 실행한다.

```bash
docker compose up -d
docker compose ps
```

로컬 backend는 아래 주소로 연결한다.

| 서비스 | 주소 |
|---|---|
| PostgreSQL | `localhost:55432` |
| MinIO S3 API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |
| Ollama | `http://localhost:11434` |

## 2. 환경 파일과 Python 의존성

```bash
cd backend
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

`backend/.env`는 로컬 실행용이므로 `DATABASE_URL`의 host는 `localhost`, `S3_ENDPOINT_URL`과 `OLLAMA_BASE_URL`도 `localhost`를 유지한다. 비밀 값은 Git에 올리지 않는다.

## 3. 로컬 API 실행

DB schema를 최초 한 번 적용합니다.

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```

그 다음 API를 실행합니다.

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Health: `http://localhost:8000/api/v1/health`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 카카오 로그인·관리자 등록 설정

`backend/.env`에 카카오 개발자 콘솔의 REST API 키와 backend callback URL을 설정한다. 콘솔 Redirect URI는 `KAKAO_REDIRECT_URI`와 정확히 일치해야 한다.

```dotenv
KAKAO_REST_API_KEY=...
KAKAO_CLIENT_SECRET=... # 카카오 콘솔에서 클라이언트 시크릿을 사용 설정한 경우
KAKAO_REDIRECT_URI=http://localhost:8000/api/v1/auth/kakao/callback
FRONTEND_LOGIN_CALLBACK_URL=http://localhost:5173/auth/callback
ADMIN_SIGNUP_CODE=change-this-local-code
```

첫 카카오 로그인 뒤 역할 선택 화면이 나타난다. `ADMIN`은 `ADMIN_SIGNUP_CODE`가 일치할 때만 선택할 수 있으며, 실제 값은 저장소에 커밋하지 않는다. 관리자 PDF 업로드는 private MinIO bucket에 짧은 만료의 presigned PUT URL로 전송한 뒤 서버가 SHA-256·파일 크기·PDF 페이지 수를 다시 검증한다.

## 4. Ollama 모델 준비

모델 파일은 처음 한 번만 받는다. RAG 구현 전에는 내려받지 않아도 API health check는 동작한다.

```bash
docker compose exec ollama ollama pull qwen3:8b
docker compose exec ollama ollama pull qwen3-embedding:4b
docker compose exec ollama ollama list
```

모델/임베딩 선택 및 Elasticsearch 도입 기준은 [인프라·검색·로컬 AI 선정](../docs/인프라_및_로컬AI_선정.md)을 따른다.

## 검사

```bash
cd backend
source .venv/bin/activate
python -m compileall -q app
pytest
ruff check .
```
