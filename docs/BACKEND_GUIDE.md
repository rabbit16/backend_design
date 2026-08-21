# 后端运行手册

适老化语音问答 App 的 FastAPI 后端：启动、数据库迁移、改配置。

项目根目录：

```bash
cd /home/westwell/haolliang.jiang/python_proj/backend_design
```

---

## 1. 首次准备

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 复制配置（若还没有 .env）
cp .env.example .env
```

确保本机 MySQL 已启动，并建好库（默认库名 `senior_voice`）：

```bash
# 用 Python 建库示例（无 mysql 客户端时）
python - <<'PY'
import pymysql
conn = pymysql.connect(host="127.0.0.1", user="root", password="123456", port=3306)
with conn.cursor() as cur:
    cur.execute(
        "CREATE DATABASE IF NOT EXISTS senior_voice "
        "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
conn.close()
print("ok")
PY
```

或直接导入完整 SQL：

```bash
mysql -h127.0.0.1 -uroot -p123456 senior_voice < docs/database/schema.sql
```

`APP_ENV=local` 时，启动服务也会自动 `create_all` 补齐 ORM 表（方便本地开发）。

---

## 2. 启动命令

进入虚拟环境后：

```bash
source .venv/bin/activate
PYTHONPATH=. python scripts/run_dev.py
```

等价写法：

```bash
source .venv/bin/activate
PYTHONPATH=. uvicorn src.app.main:create_app --factory --host 0.0.0.0 --port 8000 --reload
```

- 默认监听：`http://0.0.0.0:8000`
- 健康检查：`GET http://127.0.0.1:8000/api/v1/health`
- API 前缀：`/api/v1`
- 开发验证码：`.env` 里 `SMS_DEV_CODE=123456`

注册示例：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/sms/send \
  -H 'Content-Type: application/json' \
  -d '{"phone":"13800138000","purpose":"register"}'

curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"phone":"13800138000","code":"123456","password":"secret12","display_name":"毕小雪"}'
```

跑测试：

```bash
source .venv/bin/activate
PYTHONPATH=. pytest -v
```

> 单测由 `tests/conftest.py` 强制使用内存 SQLite，不依赖本机 MySQL。

---

## 3. 数据库迁移命令

Alembic 封装在 `scripts/db_migrate.py`，连接串读自 `.env` 的 `DATABASE_URL`。

```bash
source .venv/bin/activate

# 查看当前版本
PYTHONPATH=. python scripts/db_migrate.py current

# 升级到最新（空库 / 已 stamp 后）
PYTHONPATH=. python scripts/db_migrate.py upgrade

# 生成迁移并立刻升级（改完 ORM 后常用）
PYTHONPATH=. python scripts/db_migrate.py migrate -m "describe change"

# 只生成 revision（不 upgrade）
PYTHONPATH=. python scripts/db_migrate.py revision -m "add xxx" --autogenerate

# 回退一版
PYTHONPATH=. python scripts/db_migrate.py downgrade -1
```

### 3.1 表已经存在时（报 1050 Table already exists）

说明：库表是之前用 `create_all` / `schema.sql` 建好的，但 `alembic_version` 为空或不对。  
这时 **不要再跑会重建旧表的 upgrade**，先把版本「盖章」到最新：

```bash
source .venv/bin/activate

# 把当前库标记为已是最新结构（不执行任何 CREATE）
PYTHONPATH=. python scripts/db_migrate.py stamp head

# 确认
PYTHONPATH=. python scripts/db_migrate.py current
# 应显示：0004_qa_multi_turn (head)
```

之后改表结构，用：

```bash
# 改 ORM → 生成差异并升级
PYTHONPATH=. python scripts/db_migrate.py migrate -m "your change"
```

启动服务：`local` 环境只会 **补缺表**，已有表不会再 CREATE，可直接：

```bash
PYTHONPATH=. python scripts/run_dev.py
```

当前迁移链（节选）：

| Revision | 说明 |
|----------|------|
| `0001_create_chat_messages` | 脚手架聊天表 |
| `0002_create_users` | 用户表 |
| `0003_domain_tables` | 业务域表 |
| `0004_qa_multi_turn` | 多轮问答消息表 |

表设计说明：`docs/database/DESIGN.md`、`docs/database/schema.sql`。

新增模型步骤：

1. 在 `src/app/db/models/` 增加/修改 ORM，并在 `__init__.py` 导出  
2. 执行 `migrate -m "..."` 或手写 `alembic/versions/`  
3. 需要时同步改 `docs/database/schema.sql`

---

## 4. 怎么改配置

### 4.1 主配置文件：`.env`

本地真实配置在项目根目录 **`.env`**（已在 `.gitignore`，不会提交）。  
模板是 **`.env.example`**，改完示例记得同步，方便同事复制。

复制并编辑：

```bash
cp .env.example .env
# 用编辑器改 .env
```

配置由 `src/app/core/config.py` 的 `Settings` 读取：环境变量优先，其次 `.env`。

### 4.2 常用项

| 变量 | 作用 | 当前本地示例 |
|------|------|----------------|
| `DATABASE_URL` | 数据库连接 | `mysql+aiomysql://root:123456@127.0.0.1:3306/senior_voice?charset=utf8mb4` |
| `HOST` / `PORT` | 监听地址端口 | `0.0.0.0` / `8000` |
| `DEBUG` | 是否热重载等 | `true` |
| `APP_ENV` | `local`/`dev`/`test`/`staging`/`prod` | `local`（local 会自动建表） |
| `REDIS_ENABLED` | 是否启用 Redis | `false`（问答上下文可回退内存） |
| `QA_CONTEXT_TTL_SECONDS` | 问答上下文固定 TTL（秒，创建时写入，提问不续期） | `2592000`（30 天） |
| `QA_CONTEXT_HISTORY_LIMIT` | 拼进模型的历史消息条数上限 | `40` |
| `JWT_SECRET_KEY` | JWT 密钥（生产务必改长密钥） | 见 `.env` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | access 有效分钟 | `120`（即 expires_in=7200） |
| `SMS_DEV_CODE` | 本地固定验证码；生产置空并接短信通道 | `123456` |
| `CORS_ORIGINS` | 跨域来源 JSON 列表 | `["*"]` |
| `API_V1_PREFIX` | HTTP 前缀 | `/api/v1` |
| `RATE_LIMIT_ENABLED` | 全局限流开关 | `true` |
| `AI_GATEWAY_PROVIDER` | 大模型网关：`echo` / `reverse-echo` / `openai` | `echo` |
| `OPENAI_API_BASE` | OpenAI 兼容 Base URL（仅 `openai`） | `https://api.openai.com/v1` |
| `OPENAI_API_KEY` | API Key | 空 |
| `OPENAI_MODEL` | 上游文本模型名 | `gpt-4o-mini` |
| `OPENAI_AUDIO_MODEL` | 语音输入→文本输出模型 | `gpt-audio` |
| `OPENAI_HTTP_PROXY` | 可选 HTTP 代理 | 空 |

### 4.2.1 切换大模型（OpenAI 协议）

业务统一走 OpenAI Python SDK（`AsyncOpenAI.chat.completions`）：文本 `messages[]`，语音为 `input_audio` + `modalities=["text"]` 流式文本。  
适老化问答 `/qa/ask`、`/qa/ask/audio` 会把历史轮次拼进 messages，再调网关。

本地默认走真实 LLM（需 Key）：

```env
AI_GATEWAY_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

离线 / 单测用 echo：

```env
AI_GATEWAY_PROVIDER=echo
```

DeepSeek 示例：

```env
AI_GATEWAY_PROVIDER=openai
OPENAI_API_BASE=https://api.deepseek.com/v1
OPENAI_API_KEY=sk-...
OPENAI_MODEL=deepseek-chat
```

改数据库账号/库名时，只改 `DATABASE_URL`，例如：

```env
DATABASE_URL=mysql+aiomysql://用户名:密码@127.0.0.1:3306/库名?charset=utf8mb4
```

改端口：

```env
PORT=8001
```

### 4.3 临时覆盖（不改文件）

```bash
DATABASE_URL=sqlite+aiosqlite:///./data/app.db \
PORT=8001 \
PYTHONPATH=. python scripts/run_dev.py
```

### 4.4 改完配置要注意

1. **改 `.env` 后重启进程**（`get_settings()` 有缓存，热重载不一定重读全部环境）。  
2. 改 `DATABASE_URL` 后若是新库：先建库 → `upgrade` 或依赖 local 的 `create_all`。  
3. 生产环境：关掉 `DEBUG`，设置强 `JWT_SECRET_KEY`，清空 `SMS_DEV_CODE`，收紧 `CORS_ORIGINS`。

---

## 5. 相关文档

| 文档 | 内容 |
|------|------|
| [`docs/API.md`](./API.md) | 接口约定 |
| [`docs/database/DESIGN.md`](./database/DESIGN.md) | 表怎么设计、怎么用 |
| [`docs/database/schema.sql`](./database/schema.sql) | MySQL 建表脚本 |
| [`README.md`](../README.md) | 脚手架总览 |

---

## 6. 速查

```bash
# 激活环境
source .venv/bin/activate

# 启动
PYTHONPATH=. python scripts/run_dev.py

# 迁移升级
PYTHONPATH=. python scripts/db_migrate.py upgrade

# 改配置
$EDITOR .env
```
