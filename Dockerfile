FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY topics.toml .
COPY src/ src/

RUN useradd --create-home bot && mkdir /data && chown bot /data
USER bot

VOLUME ["/data"]
CMD ["python", "-m", "src.main", "loop"]
