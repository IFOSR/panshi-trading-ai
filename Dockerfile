ARG NODE_VERSION=22.19.0
ARG CODEX_CLI_VERSION=0.144.6
ARG KIMI_CLI_VERSION=0.28.0

FROM node:${NODE_VERSION}-bookworm-slim AS cli-runtime
ARG CODEX_CLI_VERSION
ARG KIMI_CLI_VERSION
RUN npm install --global --omit=dev \
      "@openai/codex@${CODEX_CLI_VERSION}" \
      "@moonshot-ai/kimi-code@${KIMI_CLI_VERSION}" \
    && test "$(codex --version)" = "codex-cli ${CODEX_CLI_VERSION}" \
    && test "$(kimi --version)" = "${KIMI_CLI_VERSION}"

FROM python:3.12-slim-bookworm AS app-runtime
WORKDIR /app
COPY pyproject.toml .
COPY src ./src
COPY alembic.ini .
COPY alembic ./alembic
RUN pip install --no-cache-dir . uvicorn
RUN useradd --create-home --uid 10001 trading \
    && mkdir -p /home/trading/.codex /home/trading/.kimi-code /app/data/images \
    && chown -R trading:trading /home/trading /app/data
ENV PYTHONPATH=/app/src

FROM app-runtime AS worker
ARG CODEX_CLI_VERSION
ARG KIMI_CLI_VERSION
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libatomic1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=cli-runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=cli-runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex \
    && ln -s /usr/local/lib/node_modules/@moonshot-ai/kimi-code/dist/main.mjs /usr/local/bin/kimi \
    && test "$(codex --version)" = "codex-cli ${CODEX_CLI_VERSION}" \
    && test "$(kimi --version)" = "${KIMI_CLI_VERSION}"
USER trading
CMD ["python", "-m", "trading_agent.workflows.worker"]

FROM app-runtime AS api
USER trading
CMD ["sh", "-c", "alembic upgrade head && uvicorn trading_agent.api.app:app --host 0.0.0.0 --port 8000"]
