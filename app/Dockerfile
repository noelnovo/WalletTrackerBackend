FROM python:3.12-alpine

RUN apk add --no-cache \
    ca-certificates \
    mariadb-dev \
    gcc \
    musl-dev \
    build-base \
    linux-headers

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . .

RUN addgroup -S appgroup && adduser -S appuser -G appgroup \
    && chown -R appuser:appgroup /app

USER appuser

EXPOSE 5000
CMD ["uv", "run", "--frozen", "uwsgi", "--http", "0.0.0.0:5000", "--wsgi-file", "main.py", "--callable", "app"]
