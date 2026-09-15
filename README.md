# CarMe

선택한 차량에 적용되는 공식 매뉴얼을 검색해, 근거 페이지와 함께 답하는 차량 매뉴얼 RAG 서비스입니다.

## 개발 시작

1. 환경 파일을 만듭니다.

   ```bash
   cp backend/.env.example backend/.env
   cp frontend/.env.example frontend/.env
   ```

2. Docker 서비스를 시작합니다.

   ```bash
   docker compose up --build
   ```

3. 접속 주소

   - Frontend: `http://localhost:5173`
   - FastAPI docs: `http://localhost:8000/docs`
   - MinIO console: `http://localhost:9001`

현재 API는 `/api/v1/health` 헬스체크만 제공합니다. 구현 순서는 [backend/schedule.md](backend/schedule.md), [frontend/schedule.md](frontend/schedule.md), [db/schedule.md](db/schedule.md)를 따릅니다.
