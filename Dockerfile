# syntax=docker/dockerfile:1.7
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip \
    python -c "from pathlib import Path; import tomllib; data = tomllib.loads(Path('pyproject.toml').read_text(encoding='utf-8')); deps = data.get('project', {}).get('dependencies', []); Path('/tmp/requirements.txt').write_text('\n'.join(deps) + '\n', encoding='utf-8')" \
    && pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt

COPY src ./src

EXPOSE 8000

CMD ["uvicorn", "secretary_ai.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--app-dir", "src"]
