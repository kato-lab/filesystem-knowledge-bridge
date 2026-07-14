FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md README.ja.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["kb-mcp"]
