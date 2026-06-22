# ============================================================
# MC Server Monitor - Dockerfile
# ============================================================
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --shell /bin/bash mcmonitor && \
    mkdir -p /app/data && \
    chown -R mcmonitor:mcmonitor /app && \
    chmod -R u+rw /app

USER mcmonitor

ENV MCMONITOR_ENV=production
ENV MCMONITOR_HOST=0.0.0.0
ENV MCMONITOR_PORT=5000
ENV MCMONITOR_NOBROWSER=1

EXPOSE 5000

CMD ["python", "main.py"]