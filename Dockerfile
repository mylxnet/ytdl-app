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
# 必须单 worker：TASKS / _queue 都是进程内状态，多 worker 会各持一份互不可见，
# 导致 SSE 连接落到另一个 worker 时查不到任务（表现为「页面进度不动、文件其实已下载」）。
# 用 gthread 线程池替代多进程：SSE 只占一个线程，不再独占整个 worker。
CMD ["gunicorn", "-w", "1", "-k", "gthread", "--threads", "8", "-b", "0.0.0.0:8765", "--timeout", "7200", "app.main:app"]
