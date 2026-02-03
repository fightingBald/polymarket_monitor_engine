FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY config /app/config

RUN uv pip install --system -e .

CMD ["python", "-m", "polymarket_monitor_engine", "--config", "/app/config/config.yaml"]
