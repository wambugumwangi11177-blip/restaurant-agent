# Nightly Postgres backup, run as a Railway cron service.
#
# postgres:18-alpine so pg_dump's major version MATCHES the server
# (ghcr.io/railwayapp-templates/postgres-ssl:18). An older pg_dump refuses to
# run against a newer server; a newer one writes archives the server's
# pg_restore cannot read. If the database is upgraded, move this tag with it.
FROM postgres:18-alpine

# aws-cli speaks S3 to the Railway bucket. The fallback exists because the
# aws-cli apk lives in the community repo and has moved between Alpine
# releases — a base-image bump should not silently break backups.
RUN apk add --no-cache aws-cli \
 || (apk add --no-cache python3 py3-pip \
     && pip3 install --no-cache-dir --break-system-packages awscli)

COPY run_backup.sh /usr/local/bin/run_backup.sh
RUN chmod +x /usr/local/bin/run_backup.sh

# A cron service runs the container on schedule and expects it to exit.
CMD ["/usr/local/bin/run_backup.sh"]
