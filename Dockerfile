FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --upgrade pip \
    && pip install -e .

EXPOSE 8000

CMD ["uvicorn", "secretary_ai.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--app-dir", "src"]
