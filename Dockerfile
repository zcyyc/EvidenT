FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        docker.io \
        git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /workspace/EvidenT
COPY pyproject.toml requirements.txt README.md ./
RUN uv venv /opt/evident-venv \
    && /opt/evident-venv/bin/pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PATH="/opt/evident-venv/bin:${PATH}"
CMD ["bash"]
