# PostgreSQL with the role/database initializer baked in. Coolify's compose
# deployment cannot mount repository files into containers, so the script
# ships inside the image instead of a Compose `configs:` entry. The official
# entrypoint runs it only for an empty data volume; operators rerun it by path
# to reconcile retained volumes (see docs/deploy.md).
FROM postgres:15-alpine@sha256:3d0f7584ed7d04e27fa050d6683a74746608faf21f202be78460d679cc56461f

COPY init-databases.sh /docker-entrypoint-initdb.d/10-init-databases.sh
