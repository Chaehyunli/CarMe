# CarMe RAG 검색 및 근거 응답 상세 설계

## 1. 확정 원칙

사용자가 차량을 선택하면 DB가 그 차량의 적용 매뉴얼을 먼저 결정한다. RAG는 그 매뉴얼 **내부에서만** 목차 섹션과 PDF 페이지를 찾고, 로컬 LLM은 검증된 원문 근거만 보고 답한다.

```text
차량 선택 → 메모리 채팅 세션 생성·매뉴얼 버튼 표시
질문 → 현재 READY 매뉴얼 결정 → 목차 검색 → 페이지 청크 검색 → 재정렬
     → 근거 게이트 → 로컬 LLM → citation 검증 → 페이지 근거와 함께 응답
```

- S3/MinIO는 원본 PDF 보관·다운로드용이다. 질문마다 PDF 전체를 내려받지 않는다.
- PostgreSQL/pgvector는 추출 텍스트, 목차, 페이지, 벡터를 보관한다.
- `vehicle.catalog_id → manual_applicability → READY manual` 결정은 DB가 한다. LLM/벡터 검색이 차종·연식을 추측하지 않는다.
- 모든 질문은 **현재** 연결된 `READY` 문서로 다시 검색한다. 세션에 매뉴얼 스냅샷을 저장하지 않는다.
- 세부 옵션은 모르므로 “모든 옵션이 있을 수 있음”을 전제로 설명하되, 실제 장착 여부는 확인할 수 없음을 필요한 경우 명시한다.
- citation은 영구 저장물이 아니라 이번 응답의 `manual_chunk`에서 서버가 조립하는 실시간 결과다.

## 2. 단기 채팅 세션과 매뉴얼 다운로드

### 2.1 세션 수명

`POST /chat-sessions`는 질문 없이 세션을 만든다.

1. 로그인 사용자가 자신이 선택해 둔 `vehicle_id`에 접근하는지 확인한다. 실제 차량 소유 여부·VIN은 확인하지 않는다.
2. `vehicle.catalog_id`가 `ACTIVE`이고 적용 기본 매뉴얼이 `READY`인지 확인한다.
3. 예측 불가능한 `session_id`와 `InMemoryChatMessageHistory`를 서버 RAM `SessionStore`에 넣는다.
4. 현재 문서 제목·종류·PDF 쪽수·다운로드 가능 여부를 반환한다.

대화 메시지와 citation은 DB·브라우저 저장소에 기록하지 않는다. 화면을 나갈 때 frontend가 `DELETE /chat-sessions/{sessionId}`를 호출한다. 탭 강제 종료는 보장할 수 없으므로 30분 idle TTL을 함께 둔다. API 재시작·배포·다중 worker/replica에서는 세션이 사라지며, 클라이언트는 `410 CHAT_SESSION_EXPIRED`를 받아 새 세션을 만든다. 따라서 초기 운영은 **API 1 process / worker 1개**로 한정한다.

### 2.2 채팅방 UI

```text
아반떼 2025
선택 차량의 최신 매뉴얼을 기준으로 답합니다.

[취급설명서 PDF 내려받기] [문서 정보]

무엇이 불편하신가요?
```

- 문서가 하나면 primary 문서의 다운로드 버튼을, 여러 개면 문서 정보 패널의 문서별 버튼을 표시한다.
- 다운로드 버튼은 클릭할 때 `POST /chat-sessions/{sessionId}/manuals/{manualId}/download-url`을 호출한다. 응답은 5분 만료 URL과 파일명만 담고 S3 object key/bucket은 노출하지 않는다.
- 다운로드와 질문은 매번 현재 `READY` 연결을 확인한다. 관리자가 매뉴얼을 교체·archive하면 기존 세션도 다음 요청부터 새 상태를 따른다.

### 2.3 세션 API 핵심 계약

```json
POST /chat-sessions
{ "vehicle_id": "uuid" }

201
{
  "id": "session-uuid",
  "vehicle_id": "uuid",
  "expires_at": "2026-09-15T00:30:00Z",
  "manuals": [{
    "id": "manual-uuid", "title": "아반떼 2025 취급설명서",
    "manual_type": "OWNER_MANUAL", "pdf_page_count": 444,
    "is_primary": true, "download_available": true
  }]
}
```

`GET /chat-sessions/{sessionId}/manuals`, `POST /chat-sessions/{sessionId}/manuals/{manualId}/download-url`, `POST /chat-sessions/{sessionId}/messages`, `DELETE /chat-sessions/{sessionId}`만 제공한다. 상담 이력·과거 메시지·citation 조회 endpoint는 제공하지 않는다.

## 3. PDF 적재와 `READY` 정의

```text
원본 PDF → private S3 업로드 → 해시/MIME/쪽수 재검증
→ 페이지별 텍스트·OCR → 목차/섹션 구성 → 페이지 내부 청킹 → 임베딩
→ 매뉴얼 평가 세트 통과 → READY
```

`READY`는 단순 색인 완료가 아니다. 업로드 검증, `manual_section`/`manual_chunk`/임베딩 생성, 해당 매뉴얼 평가 세트의 출시 기준 통과까지 완료했을 때만 된다. `vehicle_catalog.ACTIVE`는 기본(`is_primary`) `READY` 매뉴얼이 한 개 있을 때만 가능하다.

| 레코드 | 단위 | 역할 |
|---|---|---|
| `manual` | PDF 한 버전 | 원본·버전·상태 |
| `manual_section` | 목차 항목 | 1차 검색 범위 |
| `manual_chunk` | 페이지 내부 의미 단위 | 2차 검색과 PDF 근거 |

청킹 규칙:

1. `pdf_page_number`, `printed_page_number`, breadcrumb를 모든 청크에 기록한다.
2. 450 토큰 이하 페이지는 한 청크, 긴 페이지는 문단 경계 기준 250–450 토큰으로 나누고 최대 50 토큰 overlap을 둔다.
3. 청크는 페이지 경계를 절대 넘지 않는다. 인접 페이지는 검색 뒤 보조 문맥으로만 더하며 citation 후보로도 검증한다.
4. 표·이미지 중심 또는 빈 텍스트 페이지는 OCR 검수 대상이다. 검수 전 행동 지시의 근거로 사용하지 않는다.

## 4. 임베딩·계층형 검색·LangChain

모델 구현을 provider에 묶지 않는다.

```text
EmbeddingPort.embed(texts) -> vectors
RerankerPort.score(query, passages) -> scores
ChatModelPort.generate(messages, schema) -> structured answer
```

- `manual_section`: 문서명, 제목, breadcrumb, 페이지 범위, 요약으로 임베딩한다.
- `manual_chunk`: 문서명, breadcrumb, PDF 페이지, 원문으로 임베딩한다.
- LLM에는 인덱싱용 설명문이 아닌 원문, breadcrumb, 페이지, 내부 chunk ID만 전달한다.
- Ollama `qwen3-embedding:4b`의 실제 `/api/embed` 출력은 **2,560차원**이다. `manual_chunk.embedding`은 이 차원으로 검증 후 저장하며, 모델·차원을 바꾸면 벡터를 섞지 않고 재색인한다. pgvector 일반 HNSW의 2,000차원 제한 때문에 `halfvec(2560)` cosine HNSW 표현식 인덱스를 사용한다.
- 초기 생성 모델은 Ollama `qwen3:8b`다. 일반 매뉴얼 답변은 non-thinking의 짧은 구조화 출력으로 평가하고, provider/model 교체는 adapter 설정으로만 한다.

LangChain은 자율 Agent가 아니라 고정된 LCEL `Runnable` 체인이다. `RunnableWithMessageHistory`와 `InMemoryChatMessageHistory`를 세션 ID별 RAM 저장소에 연결한다.

```text
1. AuthorizeChatSession
2. ResolveCurrentManuals
3. SafetyClassifier
4. AmbiguityClassifier
5. SectionRetriever          - 선택 문서 목차 top 3
6. PageChunkRetriever        - 선택 섹션 페이지 청크 top 12
7. Reranker                  - top 4–6
8. EvidenceGate
9. LocalLLMAnswer            - 구조화 JSON
10. CitationValidator
11. AppendInMemoryHistory
```

`ResolveCurrentManuals`는 **매 요청마다** DB를 조회한다. history에는 동일 세션의 최근 4개 메시지와 최대 2,000 토큰만 둔다. 응답 성공·안전 폴백 뒤에만 history를 갱신하며, DB write는 없다.

| 단계 | 시작값 | 조정 기준 |
|---|---:|---|
| 섹션 검색 | top 3 | Section Recall@3 |
| 페이지 청크 검색 | top 12 | Gold Page Recall@12 |
| 재정렬/LLM 문맥 | top 4–6 | page recall, 지연 시간, 컨텍스트 길이 |
| 인접 확장 | 인용 후보 앞·뒤 1쪽 | 문장 단절 여부 |

## 5. 근거 게이트와 citation

`GROUNDED` 후보에는 다음이 모두 필요하다.

1. 현재 선택 차량의 `READY` 문서에 속한 청크다.
2. 재정렬 점수가 검증된 `support_threshold` 이상이다.
3. 질문 핵심 대상과 행동 또는 주의사항을 직접 지지한다.
4. 위험 사전 규칙에 해당하지 않고, 텍스트/OCR 품질 문제가 없다.

LLM 출력은 아래처럼 내부 chunk ID만 가리킨다.

```json
{
  "status": "GROUNDED",
  "answer": "간결한 안내",
  "steps": [{"text": "행동 안내", "citation_ids": ["C1"]}],
  "warnings": [{"text": "주의사항", "citation_ids": ["C2"]}]
}
```

`CitationValidator`는 ID가 실제 컨텍스트 청크인지, 각 행동·경고에 citation이 있는지, 인용문이 청크 실제 substring인지, manual ID가 현재 검색 대상인지 검사한다. 통과 뒤 backend가 `manual_chunk`에서 PDF/인쇄 쪽수와 짧은 quote를 채운다. 실패하면 추정 답변을 버리고 `INSUFFICIENT_EVIDENCE`로 폴백한다.

`SAFETY_ESCALATION`은 제동·조향·연기·화재·연료 누출·사고 등 위험 표현에서 RAG/LLM보다 먼저 반환한다. 이 상태는 PDF citation을 붙이지 않고, “안전한 곳에 정차”, “운행 중지”, “긴급/공식 지원에 연락” 같은 정적 안전 안내만 제공한다.

```json
{
  "result_status": "GROUNDED",
  "answer": "...",
  "citations": [{
    "manual_id": "manual-uuid",
    "manual_title": "아반떼 2025 취급설명서",
    "pdf_page_number": 146,
    "printed_page_number": "5-23",
    "quote_text": "검증된 짧은 원문"
  }]
}
```

이 citation은 응답에서만 유효하다. 사용자가 원문을 열려면 같은 세션의 문서 download URL endpoint를 호출한다. citation ID를 DB에 보관하거나 별도 URL endpoint로 조회하지 않는다.

## 6. 임계값 평가와 출시 게이트

매뉴얼 버전별로 사람이 라벨링한 근거 있음 30개, 근거 없음 10개, 모호 10개, 위험 10개 질문을 준비한다. 70% 개발용과 30% holdout을 분리한다.

| 단계 | 지표 | 출시 기준 |
|---|---|---:|
| 목차 | Section Recall@3 | 95% 이상 |
| 페이지 검색 | Gold Page Recall@12 | 95% 이상 |
| 재정렬 | Gold Page Recall@6 | 90% 이상 |
| citation | 페이지/인용 정확도 | 100% |
| 근거 없음 | 안전 폴백 비율 | 95% 이상 |
| 위험 | 안전 전환 누락 | 0건 |

`support_threshold`는 개발 세트의 reranker 점수를 sweep해, “잘못된 GROUNDED”를 최소화하면서 위 안전 기준을 만족하는 가장 낮은 값으로 정한다. 설정값, 모델 버전, 후보 수, 평가 결과는 평가 JSON과 구조화 로그에 남긴다. 기준 미달이면 threshold만 조정하지 않고 청킹·OCR·목차·임베딩·reranker를 고친 뒤 다시 평가한다.

## 7. 구현 순서

1. 차량 카탈로그와 메모리 세션/문서 다운로드 API를 만든다.
2. PDF 적재, 목차·페이지 청크·임베딩 저장을 만든다.
3. LLM 없이 검색 결과와 페이지 citation을 반환해 recall을 먼저 평가한다.
4. reranker, 로컬 LLM adapter, 고정 LangChain Runnable을 연결한다.
5. EvidenceGate, 구조화 출력, citation validator, 안전 폴백을 연결한다.
6. 매뉴얼 평가 세트를 통과한 버전만 `READY`, 기본 `READY`가 있는 차량만 `ACTIVE`로 공개한다.
