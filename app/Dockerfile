FROM python:3.12-alpine AS builder
RUN apk add --no-cache mariadb-dev gcc musl-dev linux-headers
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-alpine
ARG BUILD_REVISION=unknown
RUN python -m pip uninstall --yes pip \
    && apk add --no-cache ca-certificates mariadb-connector-c \
    && addgroup -g 10001 -S appgroup \
    && adduser -u 10001 -S -G appgroup appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --chown=10001:10001 *.py ./
COPY --chown=10001:10001 endpoints/ ./endpoints/
COPY --chown=10001:10001 exceptions/ ./exceptions/
COPY --chown=10001:10001 migrations_main/ ./migrations_main/
COPY --chown=10001:10001 migrations_tenant/ ./migrations_tenant/
COPY --chown=10001:10001 models/ ./models/
COPY --chown=10001:10001 repositories/ ./repositories/
COPY --chown=10001:10001 utils/ ./utils/
COPY --chown=10001:10001 validators/ ./validators/
RUN chown 10001:10001 /app
USER 10001:10001
EXPOSE 5000
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_BUILD_REVISION=${BUILD_REVISION} WALLET_TRACKER_REQUIRE_MANAGED_KEYS=true WALLET_TRACKER_STDOUT_LOG=true
CMD ["/app/.venv/bin/uwsgi", "--http", "0.0.0.0:5000", "--wsgi-file", "main.py", "--callable", "app", "--master", "--processes", "2", "--threads", "2", "--die-on-term", "--need-app", "--vacuum"]
