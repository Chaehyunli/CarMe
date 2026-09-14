# CarMe Database

개발 DB는 PostgreSQL 16과 pgvector 확장을 사용한다.

- 이미지: `pgvector/pgvector:pg16`
- 초기화 SQL: `init/01_extensions.sql`
- 테이블·인덱스 생성: backend Alembic migration이 담당
- 영속 볼륨: Docker Compose의 `db_data`

`docker-entrypoint-initdb.d`의 SQL은 DB 볼륨이 처음 만들어질 때만 실행된다. 이미 생성한 볼륨에서 초기화 SQL을 다시 실행해야 하면, 데이터를 보존한 뒤 migration으로 처리한다. 개발 데이터를 삭제해도 되는 경우에만 `docker compose down -v` 후 재기동한다.

스키마 기준은 [ERD 및 데이터 사전](../docs/erd_및_데이터사전.md)이다.
