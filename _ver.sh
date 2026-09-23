#!/bin/bash
# 查询容器内运行时版本（仅用于校准文档，用完即删）
docker exec ytdl-app bash -c '
echo "yt-dlp  : $(yt-dlp --version 2>/dev/null)"
echo "python  : $(python --version 2>&1)"
echo "node    : $(node --version 2>&1)"
echo "ffmpeg  : $(ffmpeg -version 2>&1 | head -1)"
echo "gunicorn: $(gunicorn --version 2>&1)"
echo "flask   : $(python -c "import flask;print(flask.__version__)" 2>&1)"
echo "image   : $(docker --version 2>/dev/null || echo n/a)"
'
