# The database image: the pinned PostgreSQL release with the first-start initialiser baked in.
#
# The initialiser used to be bind-mounted from the clone (./postgres/init). Whether Postgres
# could run it then depended on the host: Docker Desktop on macOS reported "bad interpreter:
# Permission denied" on a fresh volume, while Linux ran it (Codex completion audit,
# 19 Nov 2026). Copying it into the image with a fixed mode makes every host see the same
# file. It still runs only on an empty data volume; an existing database is never touched.
FROM postgres:17.12-trixie@sha256:0d938e975177bef9f1f61f3f9dbcf2e0aa0a139568f66d3415ed8892eb97f6ac
COPY init/ /docker-entrypoint-initdb.d/
# Owned by root, readable and executable by the postgres user that runs the entrypoint.
# A CRLF checkout (Windows git) would also break the #! line, so strip carriage returns.
RUN sed -i 's/\r$//' /docker-entrypoint-initdb.d/*.sh \
 && chown root:root /docker-entrypoint-initdb.d/* \
 && chmod 0755 /docker-entrypoint-initdb.d/*.sh
