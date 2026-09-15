# Backend 초기 MVP 체크리스트

완료한 항목은 `- [x]`로 바꾼다. 초기 DB는 [ERD](../docs/erd_및_데이터사전.md)의 8개 영구 테이블만 구현한다. 채팅은 DB가 아닌 프로세스 메모리에서만 유지한다.

## 0. 초기 구동

- [x] FastAPI, `/api/v1/health`, Dockerfile, PostgreSQL(pgvector), MinIO 추가
- [x] Ollama Docker service와 영속 모델 volume 추가
- [x] Swagger UI(`/docs`), ReDoc(`/redoc`), OpenAPI JSON과 Bearer 스키마 설정
- [ ] `docker compose up --build`로 API·DB·MinIO·frontend 동시 기동 확인
- [x] `pytest`, `ruff check .` 실행 기준 확정

## 1. DB와 인증

- [x] Alembic 및 `vector` extension migration 작성
- [x] `user`, `refresh_token`, `vehicle_catalog`, `vehicle` 모델·제약 작성
- [x] `manual`, `manual_applicability`, `manual_section`, `manual_chunk` 모델 작성
- [x] `manual_chunk`에 `pdf_page_number`, `printed_page_number`을 직접 저장
- [ ] `USER`/`ADMIN` role dependency와 카카오 OAuth, JWT, refresh token 구현
- [ ] 일반 사용자의 `/admin/*` 403, 타 사용자 리소스 403 테스트 작성

## 2. 차량·단기 채팅 API

- [x] `GET /vehicle-catalog`: `ACTIVE` + 기본 `READY` 매뉴얼 차량만 반환
- [ ] 차량 등록·목록·별칭 수정·soft delete API 구현
- [ ] `SessionStore`와 LangChain `InMemoryChatMessageHistory` 구현: 최근 4개 메시지/2,000 토큰, idle TTL 30분
- [ ] `POST/GET/DELETE /chat-sessions` 및 세션 소유권·만료(`410`) 처리 구현
- [ ] 빈 채팅방에서 현재 적용 매뉴얼 목록과 download URL API 제공
- [ ] 질문을 DB에 저장하지 않고 RAG 실행·상태별 응답 API 구현
- [ ] 화면 이탈, 차량/계정 삭제 시 메모리 세션을 제거하고 API 재시작으로 세션이 종료되는 테스트 작성
- [ ] `GROUNDED`, `AMBIGUOUS`, `INSUFFICIENT_EVIDENCE`, `SAFETY_ESCALATION` schema 확정

## 3. 관리자 차량·매뉴얼 운영

- [ ] `/admin/vehicle-catalog` 목록·생성·상세·공개/보관 API 구현
- [ ] 관리자 UI/API에 `아반떼 2025` 표시명만 반환하고 내부 코드·object key를 숨김
- [ ] 매뉴얼 초안 생성, 적용 차량 연결, 기본 매뉴얼 지정 API 구현
- [ ] PDF direct upload용 짧은 만료·고유 staging key PUT presigned URL과 완료 검증 API 구현
- [ ] `READY` 기본 매뉴얼 없이는 `ACTIVE` 공개가 409가 되는 테스트 작성
- [ ] 관리자 변경을 request ID·actor·action·target·결과로 구조화 로그 기록

## 4. S3/MinIO 적재

- [ ] private bucket 및 public-read 차단
- [ ] 파일 MIME·크기·SHA-256·PDF 페이지 수 검증
- [ ] CN7 PDF를 첫 검증 파일로 업로드
- [ ] PyMuPDF 페이지 텍스트와 목차/헤딩 추출
- [ ] 한 PDF 페이지를 넘지 않는 청크 생성 및 페이지 번호·임베딩 저장
- [ ] worker/CLI로 `UPLOADED → INDEXING → 평가 통과 → READY/FAILED` 상태 전이
- [ ] 매뉴얼 download URL API 구현

## 5. LangChain RAG

- [ ] `OllamaChatModel`/`OllamaEmbedding` adapter 구현: 기본 `qwen3:8b`, `qwen3-embedding:4b`, provider 교체 가능
- [ ] `ollama pull qwen3:8b` 및 `ollama pull qwen3-embedding:4b` 후 health/model-ready 점검 절차 추가
- [ ] 임베딩 1,024차원 고정, 모델·차원 변경 시 전체 재색인 테스트 작성
- [ ] `ManualResolver`: `vehicle.catalog_id`에서 현재 `READY` manual ID 결정
- [ ] `SectionRetriever`: manual ID 범위의 목차 1차 검색
- [ ] `ChunkRetriever`: section 범위의 pgvector 2차 검색·재정렬
- [ ] LCEL Runnable으로 분류→검색→답변→인용 검증 구성
- [ ] `RunnableWithMessageHistory`를 in-memory 세션 ID에 연결하고 단일 API process/worker 제약을 배포 설정에 반영
- [ ] citation 페이지는 LLM이 아닌 `manual_chunk`에서 backend가 확정
- [ ] 임계값/LLM 오류/검증 실패는 `INSUFFICIENT_EVIDENCE` 처리
- [ ] 요청마다 S3 PDF 전체를 내려받거나 LLM에 전달하지 않음

## 6. 검증·운영

- [ ] 초기 매뉴얼별 평가 질문: 근거 30, 범위 밖 10, 위험 10, 통합 기능 10
- [ ] Section Recall@3, Gold Page Recall@12, 인용 일치, 안전 전환 기준 측정
- [ ] 적재 뒤 수동/스크립트 평가 통과 후에만 `manual`을 `READY`, 관리자가 차량을 `ACTIVE` 공개
- [ ] 구조화 로그에 request ID, manual ID, retrieval 상태, latency 기록
- [ ] 개인정보·원문 object key·토큰이 로그에 남지 않도록 점검
