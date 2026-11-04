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
COPY *.py ./
COPY endpoints/ ./endpoints/
COPY exceptions/ ./exceptions/
COPY migrations_main/ ./migrations_main/
COPY migrations_tenant/ ./migrations_tenant/
COPY models/ ./models/
COPY repositories/ ./repositories/
COPY utils/ ./utils/
COPY validators/ ./validators/
USER 10001:10001
EXPOSE 5000
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_BUILD_REVISION=${BUILD_REVISION} WALLET_TRACKER_REQUIRE_MANAGED_KEYS=true WALLET_TRACKER_STDOUT_LOG=true
CMD ["/app/.venv/bin/uwsgi", "--http", "0.0.0.0:5000", "--wsgi-file", "main.py", "--callable", "app", "--master", "--processes", "2", "--threads", "2", "--die-on-term", "--need-app", "--vacuum"]
