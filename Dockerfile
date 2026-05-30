FROM python:3.12-slim

WORKDIR /app

# 复制包源码（保持 spider_diary/ 子目录结构）
COPY __init__.py engine.py cleanup.py ./spider_diary/
COPY cli/ ./spider_diary/cli/
COPY core/ ./spider_diary/core/
COPY report/ ./spider_diary/report/
COPY storage/ ./spider_diary/storage/
COPY remind/ ./spider_diary/remind/
COPY setup.py pyproject.toml README.md metadata.json ./

RUN pip install --no-cache-dir . && rm -rf /root/.cache /app/build /app/*.egg-info

RUN mkdir -p /app/reports /app/data

VOLUME ["/app/reports", "/app/data"]
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai
EXPOSE 8080

ENTRYPOINT ["spider-diary"]
CMD ["run"]
