# CarMe

선택한 차량에 적용되는 공식 매뉴얼을 검색해, 근거 페이지와 함께 답하는 차량 매뉴얼 RAG 서비스입니다.

## 개발 시작

1. 환경 파일을 만듭니다.

   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```

2. Docker로 의존 서비스만 시작합니다. FastAPI와 frontend는 각각 로컬 Python/Node 환경에서 실행합니다.

   ```bash
   docker compose up -d
   ```

3. 접속 주소

   - MinIO console: `http://localhost:9001`
   - Ollama (API 내부 전용): `http://localhost:11434`

3. backend와 frontend 실행 방법은 각 README를 따릅니다.

   - [backend/README.md](backend/README.md)
   - [frontend/README.md](frontend/README.md)

4. 로컬 AI 모델을 한 번 내려받습니다. 모델 파일은 약 8GB 이상이 필요합니다.

   ```bash
   docker compose exec ollama ollama pull qwen3:8b
   docker compose exec ollama ollama pull qwen3-embedding:4b
   ```

현재 API는 `/api/v1/health` 헬스체크만 제공합니다. 인프라와 모델 선정 근거는 [docs/인프라_및_로컬AI_선정.md](docs/인프라_및_로컬AI_선정.md), 구현 순서는 [backend/schedule.md](backend/schedule.md), [frontend/schedule.md](frontend/schedule.md), [db/schedule.md](db/schedule.md)를 따릅니다.
