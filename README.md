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

3. DB schema를 적용합니다. 개발용 Docker PostgreSQL은 호스트 포트 `55432`를 사용합니다.

   ```bash
   cd backend
   alembic upgrade head
   ```

4. 접속 주소

   - MinIO console: `http://localhost:9001`
   - Ollama (API 내부 전용): `http://localhost:11434`

5. backend와 frontend 실행 방법은 각 README를 따릅니다.

   - [backend/README.md](backend/README.md)
   - [frontend/README.md](frontend/README.md)

6. 로컬 AI 모델을 한 번 내려받습니다. 모델 파일은 약 8GB 이상이 필요합니다.

   ```bash
   docker compose exec ollama ollama pull qwen3:8b
   docker compose exec ollama ollama pull qwen3-embedding:4b
   ```

현재는 카카오 로그인, 첫 로그인 역할 선택, 관리자 차량 카탈로그·PDF 업로드 흐름까지 구현되어 있습니다. 실제 카카오 인증 전에는 `backend/.env`의 `KAKAO_REST_API_KEY`, `KAKAO_REDIRECT_URI`, `ADMIN_SIGNUP_CODE`를 설정해야 합니다. 차량 카탈로그는 공개 상태이고 기본 매뉴얼이 준비된 모델·연식만 반환합니다. 구현 일정은 [개발 일정](docs/개발_일정_2026-09-15.md), 세부 체크리스트는 [backend/schedule.md](backend/schedule.md), [frontend/schedule.md](frontend/schedule.md), [db/schedule.md](db/schedule.md)를 따릅니다.
