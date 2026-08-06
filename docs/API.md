# 后端 API 设计文档（FastAPI）

面向「适老化语音问答 App」的 RESTful API 约定。前端已按本约定预留 `src/services/*`。

- Base URL：`{API_BASE_URL}/api/v1`
- 前端配置文件：`config/api.json` 的 `apiBaseUrl`
- 机器可读规范：[`docs/openapi.yaml`](./openapi.yaml)（可直接导入 FastAPI / Swagger UI）

---

## 1. 通用约定

### 1.1 REST 原则

| 方法 | 用途 |
|------|------|
| `GET` | 查询资源，幂等 |
| `POST` | 创建资源，或触发非幂等动作（登录、OCR、分享） |
| `PUT` | 全量替换资源 |
| `PATCH` | 部分更新资源 |
| `DELETE` | 删除资源 |

- 资源用名词复数：`/archives`、`/family/contacts`
- 子资源：`/archives/{id}/share`
- 动作型接口仅在无法用资源语义表达时使用：`/auth/login/sms`、`/voice/recognize`

### 1.2 认证

- 登录成功后返回 JWT：`access_token` + `refresh_token`
- 受保护接口请求头：

```http
Authorization: Bearer <access_token>
```

### 1.3 统一响应

成功：直接返回资源 JSON（不包一层 `{data:...}`，便于 FastAPI 原生模型）。

失败：

```json
{
  "code": "invalid_sms_code",
  "message": "验证码错误或已过期",
  "details": {}
}
```

| HTTP | 含义 |
|------|------|
| 400 | 参数错误 |
| 401 | 未登录 / token 无效 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 冲突（如手机号已注册逻辑冲突） |
| 422 | 校验失败 |
| 429 | 限流（短信发送等） |
| 500 | 服务端错误 |

### 1.4 时间与语言

- 时间一律 ISO 8601 UTC：`2026-07-29T04:00:00Z`
- `lang` / `preferred_lang`：`zh` | `en`

### 1.5 CORS / Android 明文 HTTP

开发期若用 `http://局域网IP:8000`：

1. FastAPI 开启 CORS，允许 App 来源或 `*`
2. Android 已允许明文流量时才能用 HTTP（本项目若未开，需在 `AndroidManifest` / `networkSecurityConfig` 配置）

---

## 2. 接口清单

### 2.1 健康检查

#### `GET /health`

无需鉴权。

```json
{ "status": "ok", "version": "0.1.0" }
```

> 注意：健康检查可挂在 `/api/v1/health`，也可额外提供根路径 `/health`。

---

### 2.2 认证 Auth

#### `POST /auth/sms/send`

发送登录/注册验证码。

请求：

```json
{ "phone": "13800138000", "purpose": "login" }
```

`purpose`：`login` | `register` | `reset_password`（默认 `login`）

响应 `200`：

```json
{ "ok": true, "expire_in": 300 }
```

错误示例：`429` + `code=sms_rate_limited`

---

#### `POST /auth/register`

新用户注册（对齐 `users` 表：手机号、密码、可选昵称）。

请求：

```json
{
  "phone": "13800138000",
  "code": "123456",
  "password": "******",
  "display_name": "可选昵称",
  "preferred_lang": "zh"
}
```

响应：同短信登录（返回 token + user）。  
错误：`409` 手机号已注册；`401` 验证码无效。

---

#### `POST /auth/login/sms`

验证码登录；可选同时设置密码（对应登录页「验证码登录 + 设置密码」）。

请求：

```json
{
  "phone": "13800138000",
  "code": "123456",
  "password": "可选，首次设置"
}
```

响应 `200`：

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 7200,
  "user": {
    "id": "usr_xxx",
    "phone": "13800138000",
    "display_name": null,
    "preferred_lang": "zh",
    "created_at": "2026-07-29T04:00:00Z"
  }
}
```

---

#### `POST /auth/login/password`

请求：

```json
{ "phone": "13800138000", "password": "******" }
```

响应：同短信登录。

---

#### `POST /auth/password`（需登录）

修改/设置密码。

```json
{ "old_password": "可选", "new_password": "新密码" }
```

响应：`{ "ok": true }`

---

#### `POST /auth/logout`（需登录）

使当前 `access_token` / `refresh_token` 失效（若做服务端会话黑名单）。

响应：`{ "ok": true }`

---

#### `POST /auth/token/refresh`

```json
{ "refresh_token": "..." }
```

响应：新的 `TokenPair`（可不含 `user`）。

---

#### `GET /me`（需登录）

返回当前用户 `UserProfile`。

---

### 2.3 语音与问答 QA

适老化约定：**前端文字提问不必传 session_id**。  
服务端用 Redis（或本地内存回退）按用户缓存当前 `context_id`（即 `qa_sessions.id`）。  
**固定 30 天过期**（自上下文创建起算）：期内继续提问**不会**刷新过期时间；到期后自动换新上下文。

#### `POST /qa/ask`（需登录）——文字输入（SSE 流式）

`Content-Type: text/event-stream`

请求：

```json
{
  "question": "今天天气怎么样",
  "lang": "zh",
  "new_context": false
}
```

| 字段 | 说明 |
|------|------|
| `question` | 用户输入的文字 |
| `lang` | `zh` \| `en` |
| `new_context` | `true` 时强制新开上下文（如点「新问题」） |

事件顺序（每行 `data: {json}`，空行分隔）：

1. **meta** — 上下文信息（先返回，便于 UI 绑定）
2. **token** — 回答增量，可多次：`{"type":"token","delta":"..."}`
3. **done** — 完整结果（已落库）
4. 失败时 **error**：`{"type":"error","code":"...","message":"..."}`

示例：

```text
data: {"type":"meta","context_id":"...","context_continued":false,"lang":"zh","question_text":"今天天气怎么样","turn_index_user":1,"turn_index_assistant":2}

data: {"type":"token","delta":"今天"}

data: {"type":"token","delta":"晴朗"}

data: {"type":"done","context_id":"...","lang":"zh","question_text":"今天天气怎么样","answer_text":"今天晴朗","turn_index_user":1,"turn_index_assistant":2,"context_continued":false,"created_at":"2026-07-29T04:01:00Z"}
```

`context_continued=true` 表示沿用未过期的旧上下文（多轮追问）。

#### `POST /qa/ask/audio`（需登录）——语音输入 → 文本 SSE

`multipart/form-data`，服务端用 OpenAI SDK 以 `input_audio` 调用音频模型，**只流式返回文本**（`modalities=["text"]`）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `file` | file | wav / mp3 |
| `lang` | string | `zh` \| `en` |
| `new_context` | bool | 是否强制新上下文 |
| `prompt` | string | 可选提示语（默认适老化口语提示） |
| `audio_format` | string | 可选 `wav` \| `mp3`（不传则按文件名推断） |

事件顺序同 `/qa/ask`（meta → token* → done）。

#### `POST /qa/ask/audio/json`（需登录）——base64 语音

```json
{
  "audio_base64": "...",
  "audio_format": "wav",
  "prompt": "请用简短口语化中文回答录音里的问题。",
  "lang": "zh",
  "new_context": false
}
```

#### `POST /qa/context/clear`（需登录）

主动结束当前上下文；下次 `/qa/ask` 会新建。

响应：`{ "ok": true, "context_id": "旧id或null" }`

---

#### `POST /voice/recognize`（需登录，`multipart/form-data`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `file` | file | 音频，建议 `audio/m4a` / `audio/wav` |
| `lang` | string | `zh` \| `en` |

响应：

```json
{ "text": "今天天气怎么样", "duration_ms": 3200 }
```

---

#### `POST /qa/sessions`（需登录）

创建一次问答会话（显式管理 session 时使用；适老化文字输入请优先用 `/qa/ask`）。

```json
{
  "question": "今天天气怎么样",
  "lang": "zh",
  "audio_url": "可选，若已上传音频"
}
```

响应：

```json
{
  "session_id": "qa_xxx",
  "question_text": "今天天气怎么样",
  "answer_text": "今天晴，气温 18～26℃……",
  "lang": "zh",
  "created_at": "2026-07-29T04:01:00Z"
}
```

---

#### `GET /qa/sessions/{session_id}`（需登录）

查询单次问答。

---

#### `POST /qa/sessions/{session_id}/recommendations`（需登录）

基于该次问答生成「就医建议」卡片（对应首页「医疗推荐」按钮）。

响应：

```json
{
  "session_id": "qa_xxx",
  "title": "就医建议",
  "body": "建议附近社区医院就诊……",
  "risk_level": "low",
  "disclaimer": "本建议不能替代医生诊断"
}
```

---

### 2.4 档案 Archives（病历 OCR / 时间线）

#### `POST /archives/ocr`（需登录，`multipart/form-data`）

| 字段 | 说明 |
|------|------|
| `file` | 图片 |
| `source` | `camera` \| `album` |

响应：

```json
{
  "diagnosis": "支气管炎倾向，建议复查",
  "medicine": "按医嘱服用止咳药，注意饮水",
  "visit_date": "2026-07-27",
  "raw_ocr_text": "原始 OCR 全文……"
}
```

---

#### `GET /archives`（需登录）

查询参数：

| 参数 | 说明 |
|------|------|
| `q` | 关键词搜索 |
| `page` | 默认 1 |
| `page_size` | 默认 20，最大 100 |

响应：

```json
{
  "items": [ /* ArchiveRecord */ ],
  "total": 2,
  "page": 1,
  "page_size": 20
}
```

`ArchiveRecord`：

```json
{
  "id": "arc_xxx",
  "diagnosis": "...",
  "medicine": "...",
  "visit_date": "2026-07-27",
  "raw_ocr_text": "...",
  "image_url": "https://...",
  "created_at": "2026-07-29T04:02:00Z",
  "updated_at": "2026-07-29T04:02:00Z"
}
```

---

#### `POST /archives`（需登录）

保存 OCR 结果到档案。

```json
{
  "diagnosis": "...",
  "medicine": "...",
  "visit_date": "2026-07-27",
  "raw_ocr_text": "可选",
  "image_url": "可选"
}
```

响应：`201` + `ArchiveRecord`

---

#### `GET /archives/{id}`（需登录）

#### `PATCH /archives/{id}`（需登录）

```json
{ "diagnosis": "...", "medicine": "...", "visit_date": "2026-07-27" }
```

#### `DELETE /archives/{id}`（需登录）

响应：`{ "ok": true }`

---

#### `POST /archives/{id}/share`（需登录）

推送给子女联系人。

```json
{
  "contact_ids": ["ctc_1", "ctc_2"],
  "message": "可选留言"
}
```

响应：`{ "ok": true, "shared_count": 2 }`

---

#### `GET /archives/{id}/export`（需登录）

导出 PDF（返回可下载链接，避免直接流式大文件卡死老机型）。

```json
{
  "download_url": "https://.../tmp/xxx.pdf",
  "expires_in": 600
}
```

---

### 2.5 个人中心 Preferences / Family

#### `GET /me/preferences`（需登录）

```json
{ "preferred_lang": "zh" }
```

#### `PATCH /me/preferences`（需登录）

```json
{ "preferred_lang": "en" }
```

---

#### `GET /family/contacts`（需登录）

```json
{
  "items": [
    {
      "id": "ctc_1",
      "name": "女儿",
      "phone": "13900000001",
      "relation": "daughter",
      "created_at": "2026-07-29T04:00:00Z"
    }
  ]
}
```

#### `POST /family/contacts`（需登录）

```json
{ "name": "儿子", "phone": "13900000002", "relation": "son" }
```

#### `PATCH /family/contacts/{id}`（需登录）

#### `DELETE /family/contacts/{id}`（需登录）

---

#### `GET /family/rules`（需登录）

推送触发规则（对应个人中心开关）：

```json
{
  "on_record_saved": true,
  "on_abnormal": false,
  "on_visit": true
}
```

#### `PUT /family/rules`（需登录）

全量更新上述三个布尔字段。

---

## 3. FastAPI 落地建议

目录建议：

```text
backend/
  app/
    main.py
    api/v1/
      router.py
      auth.py
      qa.py
      archives.py
      family.py
    schemas/
    services/
    models/
  docs/  # 可直接引用本仓库 openapi.yaml
```

最小挂载示例：

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Senior Voice API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# include_router(..., prefix="/api/v1")
```

开发时可把本仓库的 `docs/openapi.yaml` 作为契约：先按 schema 写 Pydantic 模型，再实现业务。

---

## 4. 与前端页面对应关系

| App 页面 | 主要接口 |
|----------|----------|
| 注册 | `POST /auth/sms/send`（purpose=register）、`POST /auth/register` |
| 登录（验证码） | `POST /auth/sms/send`、`POST /auth/login/sms` |
| 登录（密码） | `POST /auth/login/password` |
| 首页文字输入 | `POST /qa/ask`（服务端 Redis 托管上下文，默认 30 天） |
| 首页按住说话 | `POST /voice/recognize` → `POST /qa/ask`（识别文本后提问）或显式 `/qa/sessions` |
| 首页医疗推荐 | `POST /qa/sessions/{id}/recommendations` |
| 结束当前对话 | `POST /qa/context/clear` |
| 档案 OCR | `POST /archives/ocr`、`POST /archives` |
| 档案时间线 | `GET /archives`、`GET /archives/{id}` |
| 推送子女 / 导出 | `POST /archives/{id}/share`、`GET /archives/{id}/export` |
| 个人中心 | `/me`、`/me/preferences`、`/family/*`、`POST /auth/password`、`POST /auth/logout` |

前端调用入口：

```text
src/services/authApi.ts
src/services/qaApi.ts
src/services/archiveApi.ts
src/services/profileApi.ts
src/services/http.ts
```

---

## 5. 改 IP 打包（前端）

1. 编辑 `config/api.json`：

```json
{
  "apiBaseUrl": "http://10.0.0.8:8000",
  "apiPrefix": "/api/v1",
  "timeoutMs": 30000
}
```

2. 重新打包：

```bash
npm run build:android
```

或临时覆盖：

```bash
API_BASE_URL=http://10.0.0.8:8000 npm run build:android
```

真机调试不要用 `localhost` / `127.0.0.1`，请用电脑局域网 IP。
