FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

COPY pyproject.toml README.md ./
COPY src ./src

RUN uv sync --no-dev

ENTRYPOINT []
