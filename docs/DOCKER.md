# Docker 部署指南

> **文档版本**: v1.0
> **创建日期**: 2026-05-30
> **编写人**: OWL (Migration Agent)

---

## 总览

本文档提供 spider_diary 项目的完整 Docker 部署指南，包括构建说明、卷挂载、环境变量和故障排除。

---

## 1. 系统要求

### 硬件要求

| 资源 | 最低要求 | 推荐配置 |
|------|----------|----------|
| CPU | 2核心 | 4核心或更高 |
| 内存 | 4GB | 8GB或更高 |
| 磁盘 | 20GB可用空间 | 50GB可用空间 |
| 网络 | 100Mbps | 1Gbps或更高 |

### 软件要求

| 软件 | 版本 | 说明 |
|------|------|------|
| Docker Engine | 20.10+ | 容器运行时 |
| Docker Compose | 1.29+ | 多容器编排 |
| Python | 3.12+ | 本地开发(可选) |
| Git | 2.30+ | 版本控制 |

---

## 2. 项目结构

```
spider_diary/
├── Dockerfile                # 主构建文件
├── docker-compose.yml        # 编排配置
├── .dockerignore             # 忽略文件
├── docs/                     # 文档目录
│   ├── PROJECT_HISTORY.md
│   ├── MILESTONES.md
│   ├── TECH_DEBT.md
│   ├── CONFIG_REFERENCE.md
│   └── DOCKER.md
├── reports/                  # 报告输出目录(卷挂载)
└── data/                     # 数据目录(卷挂载)
```

---

## 3. Dockerfile 详解

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e .
RUN mkdir -p /app/reports /app/data
VOLUME ["/app/reports", "/app/data"]
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["spider-diary"]
CMD ["run"]
```

### 构建说明

| 指令 | 说明 |
|------|------|
| `FROM python:3.12-slim` | 基于 Python 3.12 精简镜像 |
| `WORKDIR /app` | 设置工作目录 |
| `COPY . .` | 复制项目文件到容器 |
| `RUN pip install --no-cache-dir -e .` | 安装项目依赖 |
| `RUN mkdir -p /app/reports /app/data` | 创建报告和数据目录 |
| `VOLUME ["/app/reports", "/app/data"]` | 声明数据卷 |
| `ENV PYTHONUNBUFFERED=1` | 禁用Python输出缓冲 |
| `ENTRYPOINT ["spider-diary"]` | 设置入口命令 |
| `CMD ["run"]` | 默认执行 `spider-diary run` |

---

## 4. 构建镜像

### 基础构建

```bash
# 进入项目目录
cd E:\软件开发\spider_diary

# 构建镜像
docker build -t spider-diary:latest .

# 查看构建结果
docker images | findstr spider-diary
```

### 多平台构建

```bash
# 构建并推送多平台镜像
docker buildx build --platform linux/amd64,linux/arm64 -t spider-diary:latest .
```

### 构建参数

```bash
# 指定Python版本
docker build --build-arg PYTHON_VERSION=3.12 -t spider-diary:latest .

# 不使用缓存重新构建
docker build --no-cache -t spider-diary:latest .
```

---

## 5. Docker Compose 详解

```yaml
version: '3.8'
services:
  spider-diary:
    build: .
    container_name: spider-diary
    volumes:
      - ./reports:/app/reports
      - ./data:/app/data
    environment:
      - TZ=Asia/Shanghai
    restart: unless-stopped
```

### 服务配置

| 选项 | 值 | 说明 |
|------|-----|------|
| build | . | 从当前目录构建 |
| container_name | spider-diary | 容器名称 |
| volumes | ./reports:/app/reports, ./data:/app/data | 卷挂载 |
| environment | TZ=Asia/Shanghai | 时区设置 |
| restart | unless-stopped | 除非手动停止，否则自动重启 |

---

## 6. 卷挂载

### 当前挂载配置

| 主机路径 | 容器路径 | 用途 | 类型 |
|----------|----------|------|------|
| `./reports` | `/app/reports` | 运维报告输出 | 绑定挂载 |
| `./data` | `/app/data` | 数据存储 | 绑定挂载 |

### 扩展挂载

```yaml
volumes:
  - ./reports:/app/reports          # 报告目录
  - ./data:/app/data                # 数据目录
  - ./config:/app/config            # 配置文件(可选)
  - ./logs:/app/logs                # 日志目录(可选)
```

### 命名卷 (推荐用于生产)

```yaml
volumes:
  - spider-reports:/app/reports
  - spider-data:/app/data

volumes:
  spider-reports:
    driver: local
  spider-data:
    driver: local
```

---

## 7. 环境变量

### 当前环境变量

| 变量 | 值 | 说明 |
|------|-----|------|
| TZ | Asia/Shanghai | 容器时区 |
| PYTHONUNBUFFERED | 1 | Python无缓冲输出(Dockerfile中设置) |

### 推荐扩展环境变量

```yaml
environment:
  - TZ=Asia/Shanghai
  - PYTHONUNBUFFERED=1
  - SPIDER_LOG_LEVEL=INFO          # 日志级别
  - SPIDER_REPORT_FORMAT=json      # 报告格式
  - SPIDER_MAX_WORKERS=4           # 最大工作线程
  - SPIDER_DB_PATH=/app/data       # 数据库路径
  - SPIDER_REPORT_PATH=/app/reports # 报告路径
```

### 使用 .env 文件

创建 `.env` 文件:

```env
TZ=Asia/Shanghai
SPIDER_LOG_LEVEL=INFO
SPIDER_REPORT_FORMAT=json
SPIDER_MAX_WORKERS=4
```

在 docker-compose.yml 中引用:

```yaml
env_file:
  - .env
```

---

## 8. 运行容器

### 使用 Docker Compose (推荐)

```bash
# 启动服务
docker-compose up -d

# 查看日志
docker-compose logs -f spider-diary

# 停止服务
docker-compose down

# 重启服务
docker-compose restart spider-diary

# 查看状态
docker-compose ps
```

### 使用 Docker 命令

```bash
# 运行容器
docker run -d \
  --name spider-diary \
  -v ./reports:/app/reports \
  -v ./data:/app/data \
  -e TZ=Asia/Shanghai \
  --restart unless-stopped \
  spider-diary:latest

# 查看日志
docker logs -f spider-diary

# 停止容器
docker stop spider-diary

# 启动已停止的容器
docker start spider-diary

# 删除容器
docker rm -f spider-diary
```

### 交互式运行

```bash
# 进入容器shell
docker exec -it spider-diary /bin/bash

# 手动执行命令
docker run -it --rm spider-diary:latest run --help
```

---

## 9. 现有 Docker 镜像

项目中已存在以下 Docker 镜像:

| 镜像 | 标签 | 大小 | 用途 |
|------|------|------|------|
| spider-meta | latest | 283MB | 元数据管理 |
| spider-max | 3.0.0 | 823MB | 核心引擎 |
| spider-x-worker | test | 275MB | Worker节点 |
| spider-x-worker-node | latest | 275MB | Worker节点 |
| spider-x-worker-api | latest | 276MB | Worker API |
| spider-x-api | test | 276MB | API服务 |
| spidermax-room | 2.0.0 | 201MB | Room服务 |
| agents-agent-base | latest | 232MB | Agent基础镜像 |
| agents-mcp-router | latest | 273MB | MCP路由 |
| workflow-engine/agent-orchestrator | latest | 747MB | 工作流编排 |
| redis | 7-alpine | 57.8MB | 缓存 |
| rabbitmq | 3.12-management-alpine | 272MB | 消息队列 |

---

## 10. 多服务编排 (扩展)

```yaml
version: '3.8'
services:
  spider-diary:
    build: .
    container_name: spider-diary
    volumes:
      - ./reports:/app/reports
      - ./data:/app/data
    environment:
      - TZ=Asia/Shanghai
      - REDIS_URL=redis://redis:6379
      - RABBITMQ_URL=amqp://rabbitmq:5672
    depends_on:
      - redis
      - rabbitmq
    restart: unless-stopped
    networks:
      - spider-net

  redis:
    image: redis:7-alpine
    container_name: spider-redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    restart: unless-stopped
    networks:
      - spider-net

  rabbitmq:
    image: rabbitmq:3.12-management-alpine
    container_name: spider-rabbitmq
    ports:
      - "5672:5672"
      - "15672:15672"
    volumes:
      - rabbitmq-data:/var/lib/rabbitmq
    restart: unless-stopped
    networks:
      - spider-net

volumes:
  redis-data:
  rabbitmq-data:

networks:
  spider-net:
    driver: bridge
```

---

## 11. 监控与日志

### 查看容器日志

```bash
# 实时日志
docker-compose logs -f spider-diary

# 最近100行日志
docker-compose logs --tail=100 spider-diary

# 带时间戳的日志
docker-compose logs -t spider-diary
```

### 容器资源监控

```bash
# 查看容器资源使用
docker stats spider-diary

# 查看容器详细信息
docker inspect spider-diary

# 查看容器进程
docker top spider-diary
```

### 日志配置

```json
{
  "logging": {
    "driver": "json-file",
    "options": {
      "max-size": "10m",
      "max-file": "3"
    }
  }
}
```

在 docker-compose.yml 中:

```yaml
services:
  spider-diary:
    # ... 其他配置
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

---

## 12. 故障排除

### 常见问题

#### 1. 容器无法启动

```bash
# 检查容器状态
docker-compose ps

# 查看启动日志
docker-compose logs spider-diary

# 检查端口是否被占用
netstat -ano | findstr :8000
```

**可能原因**:
- 端口被占用
- 卷挂载路径不存在
- Dockerfile 构建失败

#### 2. 卷挂载问题

```bash
# 检查卷是否正确挂载
docker inspect spider-diary --format '{{json .Mounts}}'

# 检查主机目录权限
ls -la ./reports ./data

# Windows: 确保Docker Desktop中已共享该驱动器
# Settings → Resources → File Sharing → 添加 E:\
```

#### 3. 容器内命令执行失败

```bash
# 进入容器排查
docker exec -it spider-diary /bin/bash

# 检查Python环境
docker exec spider-diary python --version

# 检查已安装的包
docker exec spider-diary pip list
```

#### 4. 网络问题

```bash
# 检查容器网络
docker network ls
docker network inspect spider-net

# 测试容器间连通性
docker exec spider-diary ping redis
```

#### 5. 性能问题

```bash
# 查看资源使用
docker stats spider-diary

# 检查容器内进程
docker exec spider-diary ps aux

# 检查磁盘使用
docker system df
```

### 清理命令

```bash
# 清理未使用的镜像
docker image prune -a

# 清理未使用的卷
docker volume prune

# 清理所有未使用资源
docker system prune -a --volumes

# 查看磁盘占用
docker system df -v
```

---

## 13. 生产部署建议

### 安全加固

```yaml
services:
  spider-diary:
    # ... 其他配置
    read_only: true                    # 只读文件系统
    user: "1000:1000"                  # 非root用户
    security_opt:
      - no-new-privileges:true         # 禁止提权
    cap_drop:
      - ALL                            # 丢弃所有能力
    cap_add:
      - NET_BIND_SERVICE               # 仅添加必要能力
```

### 健康检查

```yaml
services:
  spider-diary:
    # ... 其他配置
    healthcheck:
      test: ["CMD", "spider-diary", "health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

### 资源限制

```yaml
services:
  spider-diary:
    # ... 其他配置
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

---

## 14. 更新与维护

### 更新系统

```bash
# 拉取最新代码
git pull origin main

# 重新构建镜像
docker-compose build --no-cache spider-diary

# 重启服务
docker-compose up -d

# 验证更新
docker-compose logs -f spider-diary
```

### 备份数据

```bash
# 备份报告数据
docker run --rm -v spider_diary_spider-reports:/data -v $(pwd):/backup alpine tar czf /backup/reports_backup_$(date +%Y%m%d).tar.gz -C /data .

# 备份数据库
docker exec spider-diary spider-diary backup --output /app/data/backup_$(date +%Y%m%d).db
```

### 回滚

```bash
# 回滚到指定版本
docker-compose down
docker pull spider-diary:previous-tag
docker-compose up -d
```

---

**文档生成时间**: 2026-05-30
**文档版本**: v1.0
