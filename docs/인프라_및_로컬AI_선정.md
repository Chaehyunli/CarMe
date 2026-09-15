# 인프라·검색·로컬 AI 선정 — 초기 MVP

## 결론

| 영역 | 초기 MVP 결정 | 역할 |
|---|---|---|
| 관계·벡터 DB | PostgreSQL 16 + pgvector | 사용자/차량/매뉴얼 메타데이터, 섹션·페이지 청크·벡터 |
| 원본 파일 | MinIO 개발 환경 → AWS S3 운영 환경 | private PDF 원본, 적재 산출물, 짧은 만료 다운로드 URL |
| 검색 엔진 | PostgreSQL 전문 검색 + pgvector | 키워드·의미 검색을 앱에서 합쳐 RAG 후보 선정 |
| 생성/임베딩 서버 | Ollama | API 내부 LangChain이 호출하는 로컬 모델 서버 |
| 생성 모델 | `qwen3:8b` | 한국어 매뉴얼 기반 구조화 답변의 기본 평가 모델 |
| 임베딩 모델 | `qwen3-embedding:4b`, 1,024차원 | 한국어/다국어 목차·페이지 청크 검색 |
| Elasticsearch | **MVP 미도입** | 아래 도입 조건이 발생할 때 별도 search service로 검토 |

MinIO와 Ollama는 DB 컨테이너에 넣지 않는다. 각각 object storage와 model server이므로 `docker-compose.yml`의 독립 서비스로 둔다. DB는 pgvector를 포함한 PostgreSQL만 담당한다.

## 1. Elasticsearch를 지금 넣지 않는 이유

Elasticsearch는 전문 검색·벡터 검색을 함께 하고 RRF 기반 hybrid search를 지원하므로, 정확한 경고등 명칭·코드 같은 키워드와 자연어 의미 검색을 함께 강화할 때 좋은 선택이다. [Elastic hybrid search 문서](https://www.elastic.co/docs/solutions/search/hybrid-search)

하지만 현재 구조는 차량이 먼저 매뉴얼을 결정하고, 그 안의 수백 페이지 청크만 검색한다. PostgreSQL에 이미 관계 데이터와 pgvector가 있으므로 Elasticsearch를 추가하면 동기화 대상, 인덱스 재생성, 접근 제어, 백업, 운영 메모리만 늘어난다. 초기에는 아래 점수로 충분히 검증한다.

```text
최종 점수 = 0.65 × vector_similarity + 0.35 × keyword_rank
```

`manual_id`, `section_id`, `locale`은 두 검색 모두에 같은 필터로 적용하고, top 12 후보를 reranker에 넘긴다. 가중치는 고정 정답 페이지 평가 세트에서 조정한다.

다음 중 하나가 확인되면 Elasticsearch를 **별도 `search` 서비스**로 추가한다. DB Dockerfile에 합치지 않는다.

1. 적재 완료 청크가 10만 개 이상이고 pgvector/FTS의 p95 검색 지연이 500ms를 넘는다.
2. 평가 세트에서 exact 기능명·경고등 코드·짧은 키워드 질문의 Gold Page Recall@12가 95%에 계속 못 미친다.
3. 자동완성, 동의어 사전, 오탈자 보정, 복잡한 전문 검색 운영이 제품 요구가 된다.
4. 검색 색인을 DB와 독립적으로 확장·운영할 근거가 생긴다.

그때도 PostgreSQL은 원본 메타데이터의 source of truth로 유지하고, worker가 `manual_chunk`를 Elasticsearch에 projection한다. 질문 API가 두 DB의 결과를 임의로 섞지 않고, 버전·manual ID·페이지 번호가 같은 projection인지 검증한다.

## 2. Ollama와 Qwen 선택

`qwen3:8b`를 기본 생성 모델로 채택한다. Qwen3는 한국어를 포함한 다국어를 지원하며, 8B 모델은 Ollama 배포 기준 약 5.2GB다. Qwen3의 thinking 기능은 일반적인 매뉴얼 질의에서 지연을 키울 수 있으므로 기본 RAG 답변은 non-thinking/짧은 구조화 출력으로 평가한다. [Qwen3 공식 소개](https://qwenlm.github.io/blog/qwen3/), [Ollama Qwen3 모델 목록](https://ollama.com/library/qwen3)

임베딩은 `qwen3-embedding:4b`를 기본으로 정하고 출력 차원은 **1,024**로 고정한다. 이 모델 계열은 다국어 검색을 지원하고 차원 설정이 가능하다. 한번 색인한 `manual_section`·`manual_chunk`는 모델 이름, 정확한 tag/digest, 출력 차원을 `embedding_model_version`에 기록한다. 모델 또는 차원이 바뀌면 기존 벡터와 섞지 않고 전량 재색인한다. [Ollama Qwen3 Embedding 문서](https://ollama.com/library/qwen3-embedding)

| 용도 | 모델 | 적합한 환경 |
|---|---|---|
| 개발 smoke test | `qwen3:4b` + `qwen3-embedding:0.6b` | 메모리가 작거나 빠른 UI/API 연결 확인 |
| MVP 평가 기준 | `qwen3:8b` + `qwen3-embedding:4b` | 검색·응답 품질 평가, 충분한 RAM/GPU/Apple Silicon |
| 이후 고성능 후보 | 더 큰 Qwen 또는 전용 reranker | 평가 세트 기준 미달이 확인된 뒤 별도 비교 |

4B/0.6B 조합은 개발 편의용일 뿐, 안전·근거 출시 기준은 8B/4B 기준 평가 결과로 판단한다.

## 3. Docker와 로컬 실행 규칙

Compose에는 `ollama` 서비스와 `ollama_data` volume을 추가했다. 모델은 자동 pull하지 않는다. 이미지와 모델 파일이 수 GB이므로 개발자가 의도적으로 한 번만 내려받는다.

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen3:8b
docker compose exec ollama ollama pull qwen3-embedding:4b
docker compose up --build
```

API 컨테이너는 내부 네트워크의 `http://ollama:11434`를 사용한다. frontend는 Ollama를 직접 호출하지 않는다. 호스트에서 점검할 때만 `http://localhost:11434` 포트를 쓴다.

macOS Docker Desktop은 컨테이너 GPU 가속을 제공하지 않으므로, Apple Silicon에서 실제 모델 평가가 느리면 host에 설치한 Ollama를 쓰고 `OLLAMA_BASE_URL=http://host.docker.internal:11434`로 바꾼다. Linux NVIDIA 운영 환경은 NVIDIA Container Toolkit을 설정한 뒤 GPU를 Ollama 컨테이너에 노출한다. [Ollama Docker 문서](https://docs.ollama.com/docker), [Ollama FAQ](https://docs.ollama.com/faq)

## 4. 검증 순서

1. `qwen3-embedding:4b`, 1,024차원으로 예시 PDF를 색인한다.
2. 키워드/벡터/hybrid 각 방식의 Section Recall@3, Gold Page Recall@12, p95 retrieval latency를 평가 세트에서 비교한다.
3. `qwen3:8b`로 citation validator까지 포함한 답변 평가를 한다.
4. 근거 부족 95% 이상 안전 폴백, 위험 누락 0건, citation 정확도 100%를 충족할 때만 해당 매뉴얼을 `READY`로 만든다.
5. 기준 미달의 원인이 검색인지 생성인지 분리해 본 뒤, 그 다음에 reranker 또는 Elasticsearch 도입을 결정한다.
