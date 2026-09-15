# CarMe RAG 검색 및 근거 응답 상세 설계

## 1. 확정한 원칙

사용자가 차량을 선택하면 서비스는 해당 차량에 적용되는 매뉴얼을 DB에서 결정한다. 그 다음 RAG는 **선택된 매뉴얼 내부에서** 질문과 관련된 목차 섹션과 PDF 페이지를 찾는다. LLM은 찾은 원문 근거만 보고 답한다.

```text
차량 선택
  → DB의 manual_applicability로 매뉴얼 ID 결정
  → 채팅방 생성 및 매뉴얼 다운로드 버튼 표시
  → 질문 입력
  → 목차 섹션 검색 → 페이지 청크 검색 → 재정렬 → 근거 게이트
  → 로컬 LLM 답변 생성 → 인용 검증 → 페이지 번호와 함께 반환
```

중요한 구분은 다음과 같다.

- **S3는 원본 PDF 보관과 다운로드용이다.** 채팅 질문마다 S3에서 PDF 전체를 내려받지 않는다.
- **DB는 검색용 텍스트·목차·페이지·벡터를 보관한다.** 적재가 끝난 `READY` 문서만 검색한다.
- **관리자 공개는 검색 범위를 바꾸는 운영 행위다.** `ACTIVE vehicle_catalog`과 연결된 `READY` 문서만 검색한다. 초기에는 대화별 문서 스냅샷을 만들지 않는다.
- **차량에서 매뉴얼을 고르는 일은 결정적 DB 조회다.** LLM이나 벡터 검색이 차종·연식을 추측하지 않는다.
- **RAG는 매뉴얼 안에서 근거 페이지를 고르는 일이다.** 예를 들어 PDF 6, 15, 146쪽이 근거라면 모두 citation으로 반환한다.

## 2. 차량 선택과 빈 채팅방

### 2.1 채팅방 생성 시점

사용자가 홈에서 등록 차량을 선택하고 `상담 시작`을 누르면 질문 없이 `POST /conversations`를 호출한다. backend는 아래를 한 트랜잭션으로 처리한다.

1. 차량 소유권을 확인한다.
2. `vehicle.catalog_id`로 `manual_applicability`를 조회한다. 해당 `vehicle_catalog`가 `ACTIVE`여야 한다.
3. 상태가 `READY`인 문서만 고른다.
4. 빈 `conversation`을 생성한다.
5. 채팅방 헤더에 보여 줄 문서 제목, 종류, 페이지 수, 다운로드 가능 여부를 반환한다.

초기에는 새 질문마다 현재 연결된 `READY` 문서를 검색한다. 매뉴얼 매핑을 바꾼 뒤에도 이미 저장한 답변의 citation은 `manual_id`와 페이지 번호로 표시된다. 과거 대화의 검색 범위까지 고정해야 할 때 `conversation_manual`을 추가한다.

### 2.2 채팅방 UI

채팅방은 첫 질문 전에도 아래를 보여 준다.

```text
아반떼 2025
선택 차량의 매뉴얼을 기준으로 답합니다.

[취급설명서 PDF 내려받기]  [문서 정보]

무엇이 불편하신가요?
```

- 적용 문서가 한 개면 primary 문서의 `PDF 내려받기` 버튼을 보여 준다.
- 사용설명서와 내비게이션 설명서처럼 여러 개면 `문서 정보` 패널에서 각 문서의 다운로드 버튼을 제공한다.
- 다운로드는 사용자 클릭 시에만 짧은 만료의 presigned URL을 발급한다. S3 object key나 bucket 이름은 frontend에 노출하지 않는다.
- 문서가 아직 `READY`가 아니면 채팅방을 만들지 않고 "매뉴얼을 준비 중입니다" 상태를 보여 준다.

## 3. API 계약 추가

### `POST /conversations`

질문 없이 채팅방을 생성하며, 적용 문서 목록을 반환한다.

```json
{
  "id": "conversation-uuid",
  "vehicle_id": "vehicle-uuid",
  "status": "OPEN",
  "manuals": [{
    "id": "manual-uuid",
    "title": "아반떼 2025 취급설명서",
    "manual_type": "OWNER_MANUAL",
    "pdf_page_count": 444,
    "is_primary": true,
    "download_available": true
  }],
  "started_at": "2026-09-15T00:00:00Z"
}
```

### `GET /conversations/{conversationId}/manuals`

현재 선택 차량에 적용되는 `READY` 문서 목록을 반환한다.

### `POST /conversations/{conversationId}/manuals/{manualId}/download-url`

대화 소유자만 실행할 수 있다. 문서가 해당 대화의 차량 `catalog_id`에 현재 연결된 `READY` 문서일 때만 5분 만료 presigned URL을 반환한다.

```json
{
  "url": "https://signed.example/...",
  "filename": "CN7_2025_ko_KR.pdf",
  "expires_at": "2026-09-15T00:05:00Z"
}
```

### 메시지 응답의 citation

`GROUNDED` 응답은 모든 근거 페이지를 배열로 반환한다. 페이지 번호는 LLM이 새로 만들지 않고 `citation → manual_chunk.pdf_page_number`에서 backend가 채운다.

```json
{
  "result_status": "GROUNDED",
  "answer": "표시등의 의미와 조치 방법은 아래 매뉴얼 페이지에서 확인할 수 있습니다.",
  "citations": [
    {
      "id": "citation-1",
      "manual_id": "manual-uuid",
      "manual_title": "아반떼 2025 취급설명서",
      "pdf_page_number": 6,
      "printed_page_number": "1-2",
      "quote_text": "원문에서 검증된 짧은 인용문"
    },
    {
      "id": "citation-2",
      "manual_id": "manual-uuid",
      "manual_title": "아반떼 2025 취급설명서",
      "pdf_page_number": 146,
      "printed_page_number": "5-23",
      "quote_text": "원문에서 검증된 짧은 인용문"
    }
  ]
}
```

`POST /citations/{citationId}/document-url`은 원문 확인용 URL에 `#page={pdf_page_number}`를 붙여 반환한다. 브라우저가 fragment 이동을 지원하지 않으면 UI는 `PDF 146쪽`을 별도로 보여 준다.

## 4. PDF 적재와 페이지 단위 데이터

### 4.1 적재 과정

```text
원본 PDF → private S3 업로드 → 해시/쪽수 검증
  → 페이지별 텍스트 추출 → 목차·제목 추출 → 섹션 구성
  → 페이지 내부 청킹 → 임베딩 → 평가 세트 검증 → READY
```

| 레코드 | 단위 | 역할 |
|---|---|---|
| `manual` | PDF 한 버전 | S3 원본과 버전·상태 관리 |
| `manual_section` | 목차 항목 | 1차 검색 범위. 상위/하위 목차를 가질 수 있음 |
| `manual_chunk` | 페이지 내부의 의미 단위 | 2차 벡터 검색 단위. `pdf_page_number`, `printed_page_number`을 가지며 반드시 한 PDF 페이지에 속함 |

### 4.2 청킹 규칙

1. 텍스트를 추출할 때 각 청크에 PDF 물리 페이지와 본문 인쇄 쪽수를 함께 기록한다.
2. 각 페이지에는 목차 breadcrumb를 붙인다. 예: `시동 및 주행 > 브레이크 > 주차 브레이크`.
3. 한 페이지가 450 토큰 이하이면 원칙적으로 한 청크다.
4. 긴 페이지는 제목·문단 경계를 우선해 250-450 토큰 청크로 나누고, 인접 청크에 최대 50 토큰 overlap을 둔다.
5. 청크는 페이지 경계를 넘지 않는다. 따라서 citation 페이지가 항상 명확하다.
6. 페이지 경계에서 문장이 끊긴 경우에는 검색 후 바로 앞·뒤 페이지의 관련 문단을 **추가 컨텍스트**로만 붙인다. 추가된 페이지도 citation 후보로 기록한다.
7. 텍스트가 비어 있거나 표·이미지가 핵심인 페이지는 worker 로그와 `manual.ingestion_error`에 기록한다. OCR 검수 전에는 그 페이지로 행동 지시를 생성하지 않는다.

## 5. 임베딩과 계층형 검색

### 5.1 모델 인터페이스

LLM, 임베딩, 재정렬 모델을 provider별 코드에 묶지 않는다.

```text
EmbeddingPort.embed(texts) -> vectors
RerankerPort.score(query, passages) -> scores
ChatModelPort.generate(messages, schema) -> structured answer
```

초기에는 모든 모델을 로컬 endpoint로 연결할 수 있게 한다. Ollama는 text embedding API를 제공하므로 local embedding provider 후보가 될 수 있다. 모델을 바꾸면 기존 벡터와 섞지 않고 `embedding_model_version`을 새로 기록하고 해당 버전을 재색인한다. [Ollama embedding 문서](https://docs.ollama.com/capabilities/embeddings)

### 5.2 색인 텍스트

`manual_section` 임베딩에는 제목, breadcrumb, 목차 설명, 페이지 범위를 넣는다.

```text
[문서] 아반떼 2025 취급설명서
[목차] 시동 및 주행 > 브레이크 > 주차 브레이크
[페이지] PDF 146-149
[내용 요약/제목] 주차 브레이크의 작동과 주의사항
```

`manual_chunk` 임베딩에는 문서 제목, breadcrumb, PDF 페이지 번호, 실제 원문을 넣는다. 검색 결과를 LLM에 넘길 때는 모델 편향을 줄이기 위해 원문·breadcrumb·페이지·chunk ID만 전달하고, 인덱싱용 메타 텍스트는 전달하지 않는다.

### 5.3 LangChain 체인

LangChain은 자율 Agent가 아니라 순서가 고정된 `Runnable` 체인으로 쓴다. Retriever는 query를 받아 `Document` 목록을 반환하는 인터페이스이며 custom retrieval 단계에도 사용할 수 있다. [LangChain retriever 문서](https://docs.langchain.com/oss/python/integrations/retrievers)

```text
1. AuthorizeConversation
2. ResolveCurrentManuals
3. SafetyClassifier
4. AmbiguityClassifier
5. SectionRetriever      - 선택 문서의 목차 섹션 top 3
6. PageChunkRetriever    - 선택 섹션의 페이지 청크 top 12
7. Reranker              - 상위 후보를 질의와 다시 비교해 top 4-6
8. EvidenceGate
9. LocalLLMAnswer        - 구조화 JSON 생성
10. CitationValidator
11. PersistMessageAndCitation
```

`SectionRetriever`와 `PageChunkRetriever`는 각각 custom LangChain Runnable 또는 BaseRetriever 구현으로 만든다. pgvector는 초기에는 exact nearest-neighbor 검색을 사용하고, 문서량·지연시간 측정 뒤 HNSW를 추가한다. pgvector는 exact/approximate 검색과 cosine distance, HNSW를 지원한다. [pgvector 문서](https://github.com/pgvector/pgvector)

### 5.4 후보 수의 초기값

| 단계 | 초기값 | 목적 |
|---|---:|---|
| 섹션 검색 | top 3 | 목차 범위를 좁힘 |
| 청크 검색 | top 12 | 관련 페이지를 놓치지 않음 |
| 재정렬 입력 | top 12 | 벡터 검색의 의미상 오차 보정 |
| LLM 컨텍스트 | top 4-6 | 근거는 충분히 주되 잡음을 제한 |
| 인접 페이지 확장 | 각 인용 후보의 앞·뒤 1쪽 | 끊긴 문맥 보완 |

이 수치는 시작값이며 평가 세트의 page recall, 지연 시간, 컨텍스트 길이를 보고 바꾼다. 초기에는 정책 버전과 후보·점수를 구조화 애플리케이션 로그와 평가 JSON에 기록한다.

## 6. 근거 게이트와 로컬 LLM 답변

### 6.1 EvidenceGate

LLM 호출 전 아래 조건을 만족해야 `GROUNDED` 후보가 된다.

1. 선택 차량의 현재 `READY` 매뉴얼 안에서 찾은 청크여야 한다.
2. 재정렬 점수가 검증된 `support_threshold` 이상이어야 한다.
3. 적어도 한 청크가 질문의 핵심 대상과 행동 또는 주의사항을 직접 포함해야 한다.
4. 위험 사전 규칙에 해당하지 않아야 한다.
5. 매뉴얼 상태가 `READY`여야 하고, 해당 청크의 텍스트가 비어 있지 않아야 한다.

조건을 충족하지 않으면 LLM에게 해결책 생성을 요청하지 않는다.

- 정보가 모자라면 `AMBIGUOUS`와 질문 하나를 반환한다.
- 문서 근거가 없으면 `INSUFFICIENT_EVIDENCE`와 상담 전환을 반환한다.
- 제동, 조향, 연기, 화재, 연료 누출, 사고 같은 위험 표현이면 `SAFETY_ESCALATION`을 먼저 반환한다.

### 6.2 LLM 입력과 출력

LLM에는 질문, 최근 같은 대화의 최대 4개 메시지, 최종 4-6개 원문 청크만 넘긴다. 매뉴얼 전체, 다른 차량 문서, S3 URL, 내부 prompt는 넘기지 않는다.

```text
[C1] manual_id=... page=6 breadcrumb=...
원문 청크

[C2] manual_id=... page=146 breadcrumb=...
원문 청크
```

LLM 출력은 자유 텍스트가 아니라 schema를 따른다.

```json
{
  "status": "GROUNDED",
  "answer": "간결한 안내",
  "steps": [
    {"text": "행동 안내", "citation_ids": ["C1"]}
  ],
  "warnings": [
    {"text": "주의사항", "citation_ids": ["C2"]}
  ]
}
```

`CitationValidator`는 다음을 코드로 검사한다.

- 출력 citation ID가 실제 LLM 컨텍스트의 chunk ID인가
- 각 행동·경고 문장에 citation이 하나 이상 있는가
- 인용문이 선택 청크의 실제 substring인가
- citation의 manual ID가 현재 검색 대상으로 결정한 매뉴얼에 속하는가

검증에 실패하면 생성 결과를 저장·표시하지 않고 `INSUFFICIENT_EVIDENCE`로 폴백한다. 페이지 번호와 URL은 검증 뒤 backend가 citation 레코드에서 채운다.

## 7. 임계값을 정하는 방법

임계값은 감으로 정하거나 모든 차종에 하나의 고정값을 쓰지 않는다. 문서 종류·임베딩 모델·재정렬 모델·언어가 바뀌면 다시 검증한다.

### 7.1 평가 데이터

각 매뉴얼 버전마다 아래를 사람이 라벨링한다.

| 집합 | 최소 수 | 라벨 |
|---|---:|---|
| 근거 있음 | 30 | 질문, 정답 section, 정답 PDF 페이지 1개 이상, 필수 경고 |
| 근거 없음 | 10 | 매뉴얼에 없는 질문, 다른 차종 질문, 가격·정비 진단 질문 |
| 모호 | 10 | 부족한 조건을 물어야 하는 짧은 질문 |
| 위험 | 10 | RAG 전에 안전 전환되어야 하는 표현 |

개발용 70%와 최종 holdout 30%를 분리한다. threshold, 후보 수, prompt는 개발용에서만 조정하고 holdout에는 마지막에 한 번만 적용한다.

### 7.2 측정 지표

| 단계 | 지표 | 출시 기준 |
|---|---|---:|
| 섹션 검색 | Section Recall@3 | 95% 이상 |
| 페이지 검색 | Gold Page Recall@12 | 95% 이상 |
| 재정렬 | Gold Page Recall@6 | 90% 이상 |
| citation | 인용 페이지 정확도 | 100% |
| 답변 | 근거 있는 행동 문장 비율 | 100% |
| 거절 | 근거 없음 질문의 안전 폴백 비율 | 95% 이상 |
| 안전 | 위험 질문의 안전 전환 누락 | 0건 |

### 7.3 threshold 선택 절차

1. holdout을 제외한 평가 질문마다 reranker 최상위 점수, 2위 점수, 정답 페이지 포함 여부, 최종 상태를 저장한다.
2. `support_threshold` 후보를 낮은 값부터 높은 값까지 sweep한다.
3. 각 후보에서 `근거 있는 질문을 답한 비율`, `근거 없는 질문을 잘 폴백한 비율`, `잘못 GROUNDED가 된 비율`을 계산한다.
4. **잘못된 GROUNDED의 비용이 높다**는 원칙으로, 근거 없음 폴백 95% 이상과 위험 누락 0건을 먼저 만족하는 가장 낮은 threshold를 선택한다.
5. 선택한 값과 모델·데이터셋·후보 수를 설정 파일과 평가 JSON에 기록한다.
6. 고정한 policy를 holdout에 평가한다. 기준에 못 미치면 threshold만 낮추지 말고 청킹, 섹션 추출, 임베딩, 재정렬을 먼저 개선한다.

점수 하나만으로 답변을 허용하지 않는다. score threshold와 원문 지지 여부, citation validator를 함께 통과해야 한다.

## 8. 구현 순서

1. 차량 카탈로그와 채팅방 생성 API를 구현한다.
2. 현재 적용 문서 목록과 다운로드 URL API를 구현한다.
3. PDF 적재에서 목차·페이지 번호가 포함된 청크·임베딩을 저장한다.
4. 페이지 citation을 먼저 반환하는 검색 API를 만든다. LLM 없이 검색 품질부터 평가한다.
5. 섹션 검색과 page recall 평가를 통과한 뒤 reranker를 붙인다.
6. 로컬 LLM adapter와 LangChain Runnable 체인을 붙인다.
7. structured output, citation validator, safety fallback을 붙인다.
8. 매뉴얼별 평가 질문을 확인한 경우에만 `READY` 검색 대상으로 전환한다.

이 순서를 지키면 LLM이 그럴듯하게 답하는 문제와 검색이 실제 페이지를 잘 찾는 문제를 분리해 디버깅할 수 있다.
