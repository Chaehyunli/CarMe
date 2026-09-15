# Database 구현 체크리스트

완료한 항목은 `- [x]`로 바꾼다. DB Dockerfile은 확장 활성화만 담당하고, 업무 테이블 변경은 항상 Alembic migration으로 관리한다.

## 0. 컨테이너 기반 설정

- [x] PostgreSQL 16 + pgvector Dockerfile 생성
- [x] 최초 DB 생성 시 `vector` extension 활성화
- [x] Docker Compose의 `db_data` 영속 볼륨 연결
- [ ] Docker 데몬 실행 후 `docker compose up --build db` 기동 확인
- [ ] `docker compose exec db psql -U carme -d carme -c '\\dx'`에서 vector 확장 확인

## 1. Alembic 기반 schema

- [x] Alembic 초기화와 `vector` extension migration 작성
- [x] 사용자·refresh token·차량 카탈로그·차량 migration 작성
- [x] manual·manual applicability migration 작성
- [x] 목차 section·페이지 번호가 포함된 chunk와 pgvector column migration 작성
- [x] 채팅·메시지·citation migration이 없는지 확인(단기 채팅은 API 프로세스 메모리)
- [x] ERD의 UNIQUE, FK, soft delete 제약 적용
- [ ] ERD의 일반 인덱스와 성능 측정 후 HNSW 인덱스 적용
- [ ] PostgreSQL 전문 검색(`tsvector`)과 pgvector hybrid 점수를 평가한다. Elasticsearch는 이 평가가 기준 미달일 때만 별도 search service로 도입한다.

## 2. 데이터 품질·운영

- [ ] CN7 예시 파일용 `vehicle_catalog`, manual applicability seed 추가
- [ ] 새 차종·연식 추가 시 `vehicle_catalog` 한 행 + manual applicability + 평가 세트를 같은 변경에 추가
- [ ] migration up/down 테스트와 빈 DB 기동 테스트
- [ ] backup/restore와 계정 삭제 보존 정책 검증
