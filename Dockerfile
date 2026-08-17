FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src
COPY Docs /app/Docs

RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir .

ENTRYPOINT ["phantom"]
CMD ["--help"]
