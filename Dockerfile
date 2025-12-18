# ======================================================================
FROM python:3.12-bullseye AS app-base
# ======================================================================
WORKDIR /app

COPY --chown=appuser:appuser requirements.txt /app
RUN set -eux; \
    groupadd --gid 1000 appuser; \
    useradd --uid 1000 --gid appuser --create-home --shell /bin/bash appuser; \
    chown -R appuser:appuser /app; \
    apt-get update; \
    apt-get install -y \
        gdal-bin \
        postgresql-client \
        gettext \
    ; \
    curl -sL https://deb.nodesource.com/setup_20.x | bash -; \
    apt-get install -y nodejs; \
    apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false; \
    rm -rf /var/lib/apt/lists/*; \
    rm -rf /var/cache/apt/archives; \
    pip install --no-cache-dir -r requirements.txt

# Install wait-for-it.sh
RUN curl -o /usr/local/bin/wait-for-it.sh https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh && \
    chmod +x /usr/local/bin/wait-for-it.sh

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# ======================================================================
FROM app-base AS development
# ======================================================================
COPY --chown=appuser:appuser dev-requirements.txt /app
RUN pip install --no-cache-dir -r dev-requirements.txt
COPY --chown=appuser:appuser . /app/
USER appuser
RUN ./build-resources
EXPOSE 8000/tcp

# ====================================================
FROM app-base AS production
# ====================================================
COPY --chown=appuser:appuser . /app/
COPY --from=development --chown=appuser:appuser /app/respa_admin/static/respa_admin /app/respa_admin/static/respa_admin
USER appuser
RUN set -eux; \
    python manage.py collectstatic; \
    python manage.py compilemessages
EXPOSE 8000/tcp
