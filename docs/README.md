# CarMe 문서 인덱스

이 폴더의 문서는 아래 우선순위로 해석한다. 구현 중 정책을 변경하면 영향받는 문서를 같은 변경에서 함께 갱신한다.

| 우선순위 | 문서 | 목적 |
|---|---|---|
| 1 | [API 명세서](./api_명세서.md) | Frontend와 FastAPI가 따라야 할 HTTP 계약 |
| 1 | [ERD 및 데이터 사전](./erd_및_데이터사전.md) | PostgreSQL schema, 관계, 제약, 인덱스의 기준 |
| 2 | [설계 요약](./hyundai_manual_rag_design_summary.md) | 제품 범위, S3 적재, LangChain 계층형 RAG 원칙 |
| 2 | [개발 아키텍처 및 구현 계획](./개발_아키텍처_및_구현계획.md) | 저장소 구조, Docker, 구현 순서 |
| 2 | [기능명세서](./기능명세서_2026-09-14.md) | 화면별 기능·수용 기준·정책 |
| 2 | [유저플로우](./유저플로우_2026-09-14.md.md) | 사용자의 화면 상태와 전환 |

## 현재 확정된 핵심 원칙

- 사용자는 모델·연식·매뉴얼 구분에 필요한 모델 변형만 선택하며, 세부 옵션·트림 구성은 등록하지 않는다.
- 선택 차량에 적용되는 `READY` 매뉴얼만 검색한다. 어떤 매뉴얼을 쓸지는 DB 매핑으로 결정한다.
- LangChain RAG는 선택된 매뉴얼 내부에서 `목차 섹션 → 페이지 청크 → 근거 검증 → 답변` 순으로 동작한다.
- PDF 원본은 private S3/MinIO에 저장한다. 사용자에게는 citation별 짧은 만료의 presigned URL만 발급한다.
- 근거 부족·위험 상황에서는 해결책을 추정하지 않는다.

## 구현 변경 규칙

1. API request/response 또는 상태값을 바꾸면 API 명세서와 frontend/backend `schedul.md`를 함께 갱신한다.
2. 테이블·필드·관계를 바꾸면 ERD와 Alembic migration을 같은 변경에 포함한다.
3. 새 차종·연식 매뉴얼을 `READY`로 만들 때는 `vehicle_catalog_variant`, `manual_applicability`, 평가 세트를 함께 추가한다.
