# CarMe 차량별 매뉴얼 기반 상담 — 설계 요약

## 1. 이번 MVP의 확정 범위

### 제품 정의

CarMe는 **등록한 차량의 공식 취급설명서에서 사용 방법·경고·점검 절차를 찾아, 원문 쪽수와 함께 안내하는 탐색 보조 서비스**다. 고장 원인 진단, 실제 장착 옵션 판정, 실시간 차량 데이터 진단, 정비 판정은 하지 않는다.

### 대상으로 확정한 데이터

| 항목 | 값 |
|---|---|
| 지원 차량 | S3에 적재되어 `READY` 상태인 현대차 모델·연식 |
| 초기 검증 파일 | `CN7_2025_ko_KR.pdf` (아반떼 CN7 2025) |
| 초기 파일 특성 | 국문 취급설명서, 444 PDF 페이지, 약 18MB, 텍스트 추출 가능 |
| 초기 파일 SHA-256 | `b197d45c76d9b1dbcc30cea739b9f33ed2e672cabc27f26ccfd5542aad518cff` |
| 문서 종류 | 차종별 사용설명서 우선. 이후 내비게이션 등 적용 문서를 추가 가능 |
| 지원 질문 | 사용 방법, 표시등/기능 설명, 매뉴얼에 명시된 점검·응급 절차 |
| 제외 | 가격·구매 가능 여부, 옵션 장착 여부 확인, 리콜 여부, 정비 진단, 실시간 상태 |

CN7 파일은 적재 파이프라인을 검증하기 위한 예시일 뿐, 제품의 지원 범위를 제한하지 않는다. 사용자는 **차량 모델과 연식(필요한 경우 모델 구분인 하이브리드·N Line 등)을 선택**하고, 서비스는 그 선택값에 적용되는 매뉴얼만 검색한다.

차량별 세부 옵션은 등록받거나 판정하지 않는다. 매뉴얼이 트림·옵션을 함께 설명하더라도 서비스는 선택 차량의 적용 매뉴얼 전체를 검색해 기능 사용법을 답한다. 화면에는 “이 서비스는 세부 옵션 구성을 확인하지 않고 차량 선택에 연결된 통합 매뉴얼을 기준으로 안내합니다”를 고지한다. 이는 장착 여부 판정 기능이 없다는 제품 전제이며, 별도의 옵션 데이터 모델이나 조건부 답변 규칙을 만들지 않는다.

### MVP 사용자 흐름

1. 카카오 로그인 후 지원 차량 목록에서 모델·연식·모델 구분을 선택해 차량을 등록한다.
2. 증상 카테고리 또는 자연어로 질문한다.
3. 위험 상황을 먼저 판정한다. 위험이면 RAG 답변을 만들지 않고 안전·공식 지원 안내를 표시한다.
4. 일반 질문이면 선택 차량에 적용되는 `READY` 매뉴얼 청크만 검색한다.
5. 근거가 충분하면 답변, 원문 인용, PDF 쪽수 링크를 저장·표시한다.
6. 근거가 부족하면 추정하지 않고 상담 전환 안내를 저장·표시한다.
7. 사용자는 차량별 과거 상담을 읽기 전용으로 조회한다.

## 2. 아키텍처 결정

초기에는 `frontend + backend(FastAPI)` **2개 배포 단위**로 시작한다. AI를 별도 HTTP 마이크로서비스로 분리하지 않는다. 여러 매뉴얼을 적재하더라도 초기 규모에서는 인증 전달, 네트워크 장애, 배포·관측 비용만 늘고 분리의 실익이 작다.

```text
Browser
  └─ Frontend
       └─ FastAPI API
            ├─ auth / vehicle / conversation API
            ├─ rag module (retrieve, rerank, answer, citation validation)
            ├─ PostgreSQL + pgvector
            └─ S3-compatible object storage

Manual ingestion command/worker
  ├─ private object storage에서 PDF 읽기
  ├─ 페이지 추출·청킹·임베딩
  └─ PostgreSQL에 문서 메타데이터·텍스트·벡터 저장
```

- 개발 환경: Docker Compose의 PostgreSQL(`pgvector` 확장)과 MinIO(S3 호환)를 사용한다.
- 운영 환경: PostgreSQL 관리형 DB와 AWS S3 등 S3 호환 스토리지로 교체한다. 애플리케이션은 S3 API만 사용한다.
- 벡터 검색: MVP는 PostgreSQL + pgvector 하나로 통일한다. FAISS와 Elasticsearch는 도입하지 않는다.
- AI 모듈: FastAPI 내부 `app/rag/` 패키지로 둔다. 문서 수·트래픽·GPU 작업량이 커졌을 때만 비동기 worker 또는 별도 AI 서비스로 분리한다.
- 원본 PDF: 공개 정적 URL이 아니라 private bucket에 저장한다. 원문 보기는 API가 발급한 짧은 만료의 presigned URL로 제공한다.

## 3. S3 저장·문서 적재 설계

### 관리자 등록과 object key 규칙

관리자는 운영 화면에서 `아반떼`, `2025`를 입력해 `아반떼 2025` 차량 카탈로그 행을 `DRAFT`로 만든 뒤 매뉴얼을 연결한다. 아래 object key는 시스템 내부용이며 관리자·일반 사용자 화면에 표시하지 않는다.

```text
manuals/hyundai/{model-code}/{model-year}/{locale}/{manual-type}/{source-filename}.pdf
derived/hyundai/{model-code}/{model-year}/{locale}/{manual-type}/{sha256}/pages.jsonl
derived/hyundai/{model-code}/{model-year}/{locale}/{manual-type}/{sha256}/ingestion-manifest.json
```

- 업로드 전 SHA-256을 계산하고, 이미 같은 해시가 있으면 재업로드·재색인하지 않는다.
- `ingestion-manifest.json`에는 소스 URL, 수집 일시, 파일 해시, 추출기/청커/임베딩 모델 버전, 성공·실패 상태를 기록한다.
- PDF 원본과 추출 산출물은 private bucket에 둔다. DB에는 object key와 메타데이터만 저장한다.
- 원문 보기 API는 인용 쪽수 정보를 함께 반환한다. `#page={pdf_page}` fragment가 지원되지 않는 브라우저에서는 PDF를 열고 쪽수를 화면에 별도 표시한다.

### 적재 파이프라인

1. 원본 PDF를 object storage에 업로드하고 해시·크기·쪽수를 검증한다.
2. PyMuPDF로 PDF 페이지별 텍스트를 추출한다. 이미지 전용 페이지 또는 빈 텍스트는 `extraction_status`에 남기고 필요 시 OCR 대상이 된다.
3. PDF 내장 목차(있으면)와 본문 제목을 추출해 `manual_section`을 만든다. 내장 목차가 없으면 매뉴얼의 인쇄 목차·폰트 제목·페이지 번호로 섹션을 구성하고 검수한다.
4. 각 섹션을 페이지 경계 안에서 250~450 토큰 수준의 청크로 나눈다. 섹션은 여러 페이지를 포함할 수 있지만 청크는 한 PDF 페이지를 넘지 않는다.
5. 각 청크에 `manual_id`, `section_id`, `pdf_page_number`, `printed_page_number`, `content`, `embedding_model_version`을 부여하고 BGE-M3 등 확정한 다국어 임베딩 모델로 벡터를 생성해 pgvector에 저장한다.
6. 표본 20개 이상에서 목차-섹션-본문 연결, 추출 텍스트, PDF 페이지·인쇄 쪽수 대응을 수동 검수한 뒤 `READY`로 전환한다.

`PDF 페이지`와 매뉴얼 본문의 `인쇄 쪽수`는 다를 수 있으므로 둘을 구분한다. 링크에는 PDF 페이지를 사용하고, 근거 카드에는 가능하면 `PDF 87쪽 / 본문 5-23쪽`처럼 함께 표시한다.

### 관리자 공개 게이트

1. `ADMIN`이 차종과 연식으로 차량 카탈로그 행을 `DRAFT`로 생성한다.
2. 매뉴얼 초안을 만들어 적용 차량과 기본 문서 여부를 연결한다.
3. browser direct upload의 짧은 만료 PUT URL로 PDF 하나를 업로드하고, 서버/worker가 hash·MIME·쪽수를 재검증한다.
4. 적재와 초기 평가 질문 확인이 끝나 `manual.status = READY`가 된다.
5. 기본 `READY` 매뉴얼이 있는 차량 카탈로그 행만 `ACTIVE`로 공개한다.

운영 UI는 object key, bucket, presigned URL, 장기 자격증명을 표시하지 않는다. 개정 PDF는 기존 `READY` 문서를 변경하지 않고 새 `manual` 버전으로 생성한다. 초기에는 대화 문서 스냅샷을 만들지 않지만, 저장된 citation은 매뉴얼과 페이지를 직접 가리킨다.

## 4. 검색·답변·안전 규칙

### 요청 분기

| 분기 | 처리 |
|---|---|
| 위험 신호 | RAG 생략, 안전 안내와 공식 지원 경로 표시 |
| 지원 범위 밖 질문 | `INSUFFICIENT_EVIDENCE`, 추정 금지 |
| 정보가 부족한 질문 | `AMBIGUOUS`, 차량 상태·표시등·발생 조건을 짧게 되묻기 |
| 근거가 충분한 질문 | `GROUNDED`, 매뉴얼 기반 답변과 인용 표시 |

위험 신호 사전 규칙은 최소한 제동 불능/조향 이상/연기·화재·연료 누출 의심/주행 중 심한 이상/사고 상황을 포함한다. 정확한 문구와 연결 번호는 서비스 오픈 전 안전 책임자 또는 공식 지원 정책에 맞춰 확정한다. 위험 신호에는 해결 절차를 추정해 생성하지 않는다.

### LangChain 기반 계층형 RAG와 GROUNDED 판정

차량 선택이 매뉴얼을 고르는 일은 RAG가 아니라 DB의 결정적 매핑이다. RAG는 **선택된 매뉴얼 안에서** 어떤 목차 섹션과 페이지 청크가 질문의 근거인지 찾는다. 요청마다 S3의 PDF 전체를 다운로드하거나 LLM에 통째로 넣지 않는다. 적재 시 DB에 저장한 섹션·페이지·청크·벡터를 사용하고, S3는 원문 확인용 PDF를 제공한다.

1. `ManualResolver`가 선택 차량의 `ACTIVE vehicle_catalog`에 `manual_applicability`로 연결되고 상태가 `READY`인 manual ID 목록을 DB에서 구한다.
2. `SectionRetriever`가 그 manual ID 안에서 질문과 가까운 목차 섹션을 1차로 고른다. 제목·목차 임베딩과 키워드를 함께 사용하며, 상위 3개 섹션 수는 설정값으로 관리한다.
3. `ChunkRetriever`가 선택 섹션과 manual ID로 필터링한 pgvector 검색으로 실제 페이지 청크를 2차 검색·재정렬한다. 이 단계의 상위 청크와 점수 임계값도 설정값으로 관리한다.
4. LangChain의 `Runnable` 체인(`분류 → 문서해결 → 섹션검색 → 청크검색 → 답변생성 → 인용검증`)이 최근 4개 메시지(총 2,000 토큰 이내)와 최종 청크만 LLM에 전달한다. 자율적으로 도구를 선택하는 Agent는 MVP에 사용하지 않는다.
5. 답변의 조치·주의 문장마다 근거 청크가 있어야 하며, 인용 스니펫은 LLM 생성문이 아닌 원문에서 잘라 저장한다.
6. 모델 출력, 인용 검증 또는 임계값 검사가 실패하면 답변을 버리고 `INSUFFICIENT_EVIDENCE`로 처리한다.

매뉴얼의 `경고`, `주의`, `금지` 표시는 답변 요약 중 제거하지 않는다. 옵션·트림 관련 내용도 선택 차량에 연결된 통합 매뉴얼의 기능 안내로 처리하며, 서비스가 세부 장착 구성을 판정하지 않는다는 고지만 일관되게 표시한다.

## 5. 데이터 모델

필드 정의, 제약, 인덱스, 삭제 규칙의 기준 문서는 [ERD 및 데이터 사전](./erd_및_데이터사전.md)이다. 아래는 설계 개요다.

```text
USER 1 ─ N VEHICLE 1 ─ N CONVERSATION 1 ─ N MESSAGE 1 ─ N CITATION
VEHICLE_CATALOG N ─ N MANUAL (MANUAL_APPLICABILITY)
MANUAL 1 ─ N MANUAL_SECTION 1 ─ N MANUAL_CHUNK
MANUAL 1 ─ N MANUAL_CHUNK
```

### 핵심 테이블과 제약

| 테이블 | 필수 필드·규칙 |
|---|---|
| `user` | `id`, `kakao_subject`(UNIQUE), `role`(`USER`/`ADMIN`), `created_at`, `last_login_at`; 전화번호는 수집하지 않음 |
| `vehicle_catalog` | `manufacturer`, `model_name`, `model_year`, 서버 생성 `display_name`, `status`; 한 행이 `아반떼 2025`이며 옵션·트림은 저장하지 않음 |
| `vehicle` | `id`, `user_id`, `catalog_id`, `nickname`, `created_at`; 세부 옵션·트림 구성은 저장하지 않음 |
| `manual` | `id`, `title`, `type`, `locale`, `source_url`, `object_key`, `sha256`(UNIQUE), `pdf_page_count`, `status`, `created_by`, `indexed_at`; 새 PDF는 새 버전으로 생성 |
| `manual_applicability` | `manual_id`, `catalog_id`, `is_primary`; 사용자 차량이 아니라 카탈로그 기준으로 문서 적용 범위를 관리. 한 차량에 사용설명서·내비게이션 등 여러 문서를 연결 가능 |
| `manual_section` | `id`, `manual_id`, `parent_section_id` nullable, `title`, `toc_order`, `pdf_page_start`, `pdf_page_end`, `retrieval_text`; 목차 기반 1차 검색 단위 |
| `manual_chunk` | `id`, `manual_id`, `section_id`, `pdf_page_number`, `printed_page_number`, `content`, `embedding`; 페이지 근거를 찾는 2차 검색 단위. 한 페이지를 넘지 않음 |
| `conversation` | `id`, `vehicle_id`, `status`, `started_at`; 사용자 소유권은 vehicle을 통해 검증 |
| `message` | `id`, `conversation_id`, `role`, `content`, `result_status`, `created_at`; 사용자 질문과 시스템 응답 모두 저장 |
| `citation` | `message_id`, `manual_id`, `manual_chunk_id`, `quote_text`, `pdf_page_number`; 원문 인용만 저장 |

초기에는 `VEHICLE_OPTION`과 가격 테이블을 만들지 않는다. 후속 단계에서 가격을 지원할 때는 개인 차량 옵션과 카탈로그 옵션을 분리한 `OPTION_CATALOG`, `TRIM_OPTION_AVAILABILITY`, `VEHICLE_INSTALLED_OPTION` 모델을 새로 설계한다.

## 6. API 계약

상세 endpoint, request/response, 오류 계약의 기준 문서는 [API 명세서](./api_명세서.md)다. 모든 보호 API는 access JWT를 요구하고, `conversation → vehicle → user` 경로로 소유권을 확인한다.

핵심 public API는 카카오 로그인, 차량 카탈로그·등록, 차량별 상담, citation PDF URL 발급, 계정 삭제로 구성한다. 메시지 API는 `GROUNDED`, `AMBIGUOUS`, `INSUFFICIENT_EVIDENCE`, `SAFETY_ESCALATION` 상태를 문자열 답변과 분리해 반환한다. 근거 부족·모호·안전 전환 상태에는 근거 없는 해결책을 반환하지 않는다.

차량을 선택해 채팅방을 만들면 질문 없이 현재 적용 매뉴얼 목록을 반환한다. 채팅방 헤더의 매뉴얼 다운로드와 답변 citation 페이지 처리 규칙은 [RAG 검색 및 근거 응답 상세 설계](./RAG_검색_및_근거응답_상세설계.md)를 따른다.

## 7. 수용 기준과 검증

구현 전에 **적재한 모델·연식별** 평가 세트를 만든다. 초기 CN7 2025 파일은 첫 세트로 사용하며, 새 매뉴얼을 `READY`로 전환하기 전 같은 형식의 평가 세트를 통과해야 한다. 각 세트는 매뉴얼 근거 질문 30개, 범위 밖 질문 10개, 위험 전환 질문 10개, 통합 매뉴얼 기능 질문 10개로 구성한다.

- 근거 질문: 정답과 정확한 PDF 페이지 인용이 90% 이상
- 범위 밖 질문: 추정 답변 미생성이 95% 이상
- 위험 질문: 안전 전환 누락 0건
- 인용 스니펫: 실제 저장 원문과 일치 100%
- 대표 질의: P95 응답 시간 8초 이하
- 접근 제어: 타 사용자 vehicle/conversation/citation 요청은 모두 403
- 관리자 공개: 기본 `READY` 매뉴얼이 없는 `ACTIVE` 전환 0건

## 8. 후속 확장 조건

새 차종·연식을 추가할 때마다 `vehicle_catalog` 한 행, `manual_applicability`, 적재 manifest, 평가 세트를 함께 추가한다. 같은 모델·연식의 별도 매뉴얼 적용 단위가 실제로 필요해질 때만 variant 테이블을 추가한다. AI 서비스를 분리하는 기준은 최소한 비동기 적재 작업이 API worker를 지속적으로 점유하거나, 별도 GPU 추론·독립 확장·서로 다른 배포 주기가 실제로 필요한 시점이다.
