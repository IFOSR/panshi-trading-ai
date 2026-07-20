FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY src ./src
RUN pip install --no-cache-dir . uvicorn
ENV PYTHONPATH=/app/src
CMD ["uvicorn", "trading_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
