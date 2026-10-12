FROM node:22-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Copy a compatible Node.js runtime into the Python application image.
FROM node:22-bookworm-slim AS node-runtime

FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PI_CODING_AGENT_EXECUTABLE=pi

# Pi Coding Agent requires Node.js.
COPY --from=node-runtime /usr/local/ /usr/local/

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Pin the CLI version for a repeatable build.
RUN npm install --global @mariozechner/pi-coding-agent@0.73.1

# Configure Pi's Ollama-compatible OpenAI API provider.
RUN mkdir -p /root/.pi/agent && \
    printf '%s' '{"providers":{"ollama":{"baseUrl":"http://host.docker.internal:11434/v1","api":"openai-completions","apiKey":"ollama","models":[{"id":"qwen2.5:3b","name":"Qwen2.5 3B","contextWindow":32768,"maxTokens":4096,"compat":{"supportsDeveloperRole":false,"supportsReasoningEffort":false}}]}}}' \
    > /root/.pi/agent/models.json

COPY app/ ./app/
COPY scripts/ ./scripts/
COPY data/ ./data/
COPY --from=frontend-build /frontend/dist ./frontend/dist

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
