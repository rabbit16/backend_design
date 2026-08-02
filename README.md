# AI FastAPI Backend Scaffold

一个面向高并发 AI 后端的 FastAPI 脚手架，适合复制为新项目基础模板。

## 特性

- 应用工厂 `create_app()`，方便测试、部署、多实例运行
- HTTP 路由与 WebSocket 路由统一注册
- 中间件统一注册：Request ID、访问日志、错误边界、CORS
- 结构化日志，适合接入 ELK、Loki、OpenTelemetry
- AI Gateway 抽象层，默认 echo 实现，可替换 OpenAI、Claude、本地模型或 RAG
- WebSocket 连接管理，支持连接注册、注销、单播、广播
- SQLAlchemy async ORM + Alembic 迁移，一键生成并执行数据库迁移
- async-first 设计，适合高并发 I/O 场景

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
PYTHONPATH=src python scripts/run_dev.py
```

或：

```bash
PYTHONPATH=src uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

## 数据库迁移

默认使用 SQLAlchemy async ORM + Alembic。数据库通过 `.env` 里的 `DATABASE_URL` 切换。

支持三种常用 async 数据库连接：

```env
# 本地 SQLite，默认配置
DATABASE_URL=sqlite+aiosqlite:///./data/app.db

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/app

# MySQL
DATABASE_URL=mysql+aiomysql://user:password@localhost:3306/app?charset=utf8mb4
```

切换数据库时只需要改 `.env` 的 `DATABASE_URL`，然后对目标数据库执行迁移。

一键生成迁移并升级到最新版本：

```bash
PYTHONPATH=src python scripts/db_migrate.py migrate -m "describe change"
```

常用命令：

```bash
PYTHONPATH=src python scripts/db_migrate.py upgrade
PYTHONPATH=src python scripts/db_migrate.py revision -m "add table" --autogenerate
PYTHONPATH=src python scripts/db_migrate.py downgrade -1
```

新增模型时：

1. 在 `src/app/db/models/` 新增 SQLAlchemy model。
2. 在 `src/app/db/models/__init__.py` 导入该 model，确保 Alembic 能发现 metadata。
3. 执行 `scripts/db_migrate.py migrate`。

## 验证

```bash
python -m compileall src tests
pytest
```

## HTTP 示例

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/chat/models
curl -X POST http://localhost:8000/api/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"echo","message":"hello"}'
```

## JWT 鉴权

开发模板提供 `/api/v1/auth/token` 用于生成示例 token。生产环境应接入真实用户系统，并修改 `JWT_SECRET_KEY`。

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/token \
  -H 'Content-Type: application/json' \
  -d '{"subject":"user-1"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://localhost:8000/api/v1/chat/secure-completions \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"model":"reverse-echo","message":"hello"}'
```

## Redis、限流、任务队列、链路追踪

- Redis：设置 `REDIS_ENABLED=true` 后启用 Redis 连接池，限流自动使用 Redis 计数。
- 限流：`RATE_LIMIT_REQUESTS` + `RATE_LIMIT_WINDOW_SECONDS` 控制窗口限流。
- 后台任务：`src/app/tasks/queue.py` 提供进程内 async 队列；生产可替换 Celery/Dramatiq/Arq。
- OpenTelemetry：设置 `TELEMETRY_ENABLED=true`，可选 `TELEMETRY_OTLP_ENDPOINT` 上报到 collector。

示例任务接口：

```bash
curl -X POST http://localhost:8000/api/v1/tasks/demo \
  -H "Authorization: Bearer $TOKEN"
```

## WebSocket 示例

连接：`ws://localhost:8000/ws/v1/chat/{client_id}`

发送：

```json
{"message":"hello websocket"}
```

## 新增 HTTP 路由

1. 在 `src/app/api/http/` 下新增 router 文件。
2. 在 `src/app/api/router.py` 的 `register_routes()` 中 include。

## 新增 WebSocket 路由

1. 在 `src/app/api/ws/` 下新增 router 文件。
2. 在 `src/app/api/router.py` 的 `register_routes()` 中 include。

## 替换 AI Gateway

实现 `src/app/gateways/base.py` 中的 `AIGateway` 协议，然后在 `src/app/gateways/registry.py` 根据配置返回你的实现。

## 高并发扩展建议

- 多 worker：使用 gunicorn/uvicorn worker 部署 HTTP 服务。
- WebSocket 横向扩展：将 `ConnectionManager` 的广播能力接入 Redis Pub/Sub、NATS 或 Kafka。
- AI 调用：使用 async HTTP client，设置超时、重试、限流和熔断。
- 可观测性：接入 OpenTelemetry、Prometheus、集中式日志。
