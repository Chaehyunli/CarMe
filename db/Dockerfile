FROM pgvector/pgvector:pg16

# The official image runs these only when its data volume is first initialized.
COPY init/ /docker-entrypoint-initdb.d/
