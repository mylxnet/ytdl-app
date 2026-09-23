# syntax=docker/dockerfile:1
# YouTube 下载器 — Flask + yt-dlp + ffmpeg + node(EJS 挑战)
FROM python:3.12-slim

# yt-dlp 最新版 + ffmpeg + node22（YouTube JS 挑战必需）
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && pip install --no-cache-dir yt-dlp \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY templates ./templates

RUN mkdir -p /downloads /config
ENV DOWNLOAD_DIR=/downloads COOKIES_FILE=/config/cookies.txt
VOLUME ["/downloads", "/config"]

EXPOSE 8765
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8765", "--timeout", "7200", "app.main:app"]
