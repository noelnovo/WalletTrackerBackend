FROM python:3.12-alpine AS builder
RUN apk add --no-cache mariadb-dev gcc musl-dev linux-headers
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-alpine
ARG BUILD_REVISION=unknown
RUN apk add --no-cache ca-certificates mariadb-connector-c \
    && addgroup -g 10001 -S appgroup \
    && adduser -u 10001 -S -G appgroup appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --chown=10001:10001 . .
USER 10001:10001
EXPOSE 5000
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_BUILD_REVISION=${BUILD_REVISION}
CMD ["/app/.venv/bin/uwsgi", "--http", "0.0.0.0:5000", "--wsgi-file", "main.py", "--callable", "app", "--master", "--processes", "2", "--threads", "2", "--die-on-term", "--need-app", "--vacuum"]
