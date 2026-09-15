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
| PostgreSQL | `localhost:5432` |
| MinIO S3 API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |
| Ollama | `http://localhost:11434` |

## 2. 환경 파일과 Python 의존성

```bash
cd backend
cp .env.example .env
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

`backend/.env`는 로컬 실행용이므로 `DATABASE_URL`의 host는 `localhost`, `S3_ENDPOINT_URL`과 `OLLAMA_BASE_URL`도 `localhost`를 유지한다. 비밀 값은 Git에 올리지 않는다.

## 3. 로컬 API 실행

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Health: `http://localhost:8000/api/v1/health`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

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
