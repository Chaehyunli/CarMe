# Backend 구현 체크리스트

완료한 항목은 `- [x]`로 바꾼다. 순서는 의존성을 기준으로 정했다.

## 0. 초기 구동

- [x] FastAPI 프로젝트와 `/api/v1/health` 생성
- [x] Dockerfile, PostgreSQL(pgvector), MinIO 개발 환경 추가
- [x] 환경 변수 예시와 CORS 기본 설정 추가
- [x] API 명세서와 ERD/데이터 사전 기준선 확정
- [x] Swagger UI(`/docs`), ReDoc(`/redoc`), OpenAPI JSON과 Bearer 인증 스키마 설정
- [ ] `docker compose up --build`로 API·DB·MinIO·프런트엔드 동시 기동 확인
- [ ] `pytest`와 `ruff check .`를 CI 또는 로컬 명령으로 확정

## 1. 데이터베이스와 migration

- [ ] Alembic 초기화 및 `vector` extension migration 작성
- [ ] `user`, `vehicle_catalog_variant`, `vehicle` 모델·제약 작성
- [ ] `manual`, `manual_applicability`, `manual_section`, `manual_page`, `manual_chunk`, `chunk_page` 모델 작성
- [ ] `conversation`, `message`, `citation`, `retrieval_run` 모델 작성
- [ ] `(manual_id, pdf_page_number)` UNIQUE, 파일 SHA-256 UNIQUE, 외래키·삭제 정책 적용
- [ ] 차량 선택값 → 적용 매뉴얼 관계를 위한 seed 데이터 작성
- [ ] 세부 옵션·트림·가격 테이블을 만들지 않았는지 확인

## 2. 인증·인가

- [ ] 카카오 OAuth 시작·콜백 구현
- [ ] 카카오 subject 기반 내부 사용자 생성/조회 구현
- [ ] access JWT·refresh token 발급, 회전·로그아웃 구현
- [ ] HttpOnly/Secure/SameSite cookie 및 CORS 정책 확정
- [ ] `conversation → vehicle → user` 소유권 검증 dependency 구현
- [ ] 타인 vehicle/conversation/message/citation 요청 403 테스트 작성

## 3. 차량·상담 API

- [ ] `GET /vehicle-models` 구현: `READY` 매뉴얼이 있는 모델 목록만 반환
- [ ] 연식·모델 구분 조회 API와 차량 등록/목록/수정/삭제 API 구현
- [ ] `POST /conversations`, 차량별 상담 목록, 상담 상세 API 구현
- [ ] 질문 메시지 저장 후 RAG 실행하는 메시지 API 구현
- [ ] `GROUNDED`, `AMBIGUOUS`, `INSUFFICIENT_EVIDENCE`, `SAFETY_ESCALATION` response schema 확정

## 4. S3/MinIO와 매뉴얼 적재

- [ ] private bucket 생성 및 public-read 차단
- [ ] 파일 SHA-256, MIME type, 크기, 페이지 수 검증 구현
- [ ] object key 규칙 구현: `manuals/hyundai/{model-code}/{year}/{locale}/{type}/{filename}`
- [ ] CN7 PDF를 첫 검증 파일로 MinIO에 업로드
- [ ] PyMuPDF 페이지 텍스트 추출과 빈 페이지 상태 기록 구현
- [ ] 내장 목차·본문 제목에서 `manual_section` 추출, 없을 때 목차/헤딩 폴백 구현
- [ ] 섹션 단위 청킹, 페이지 연결(`chunk_page`), 임베딩 저장 구현
- [ ] 적재 manifest와 `UPLOADED → INDEXING → READY/FAILED` 상태 전이 구현
- [ ] citation PDF용 만료 presigned URL API 구현

## 5. LangChain 계층형 RAG

- [ ] `ManualResolver`: 차량 선택값에서 `READY` manual ID를 DB로 결정
- [ ] 위험 표현 사전 분류와 `SAFETY_ESCALATION` 응답 구현
- [ ] 모호한 질문의 `AMBIGUOUS` 추가 질문 구현
- [ ] `SectionRetriever`: manual ID 범위의 목차 섹션 1차 검색 구현
- [ ] `ChunkRetriever`: 선택 section ID 범위의 페이지 청크 2차 pgvector 검색·재정렬 구현
- [ ] LCEL `Runnable` 체인으로 분류→문서결정→섹션→청크→답변→인용검증 구성
- [ ] LLM provider adapter와 prompt version 관리 구현
- [ ] 원문 substring만 citation으로 저장하도록 검증 구현
- [ ] 임계값/검증 실패/LLM 오류는 추정하지 않고 `INSUFFICIENT_EVIDENCE` 처리
- [ ] 요청 때 S3 PDF 전체를 내려받거나 LLM에 전달하지 않는지 확인

## 6. 품질·운영

- [ ] 모델·연식별 평가 세트 작성: 근거 30, 범위 밖 10, 위험 10, 통합 기능 10
- [ ] 새 매뉴얼의 `READY` 전환 전 평가 게이트 자동화
- [ ] 인용 원문 일치 100%, 위험 전환 누락 0건 테스트
- [ ] 구조화 로그에 request ID, manual ID, retrieval status, latency 기록
- [ ] 개인정보·원문 object key·토큰이 로그에 남지 않도록 점검
- [ ] 계정/차량/상담 이력 삭제 및 보존 정책 구현
