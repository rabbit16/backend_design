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

### 2.4.0 档案展示页怎么拼（给后端）

前端**不要求**统一时间线接口。展示页只读下面 5 个 GET，时间轴由前端把体检列表和就诊列表按日期倒序合并。

| 页面 | 接口 |
|------|------|
| 档案首页总结卡片 | `GET /health-summaries` |
| 时间轴 · 体检 | `GET /health-reports?page=1&page_size=100` |
| 时间轴 · 就诊 | `GET /archives?page=1&page_size=100` |
| 详情 · 体检 | `GET /health-reports/{id}` |
| 详情 · 就诊 | `GET /archives/{id}` |

约定：

- 只返回当前用户、`deleted_at IS NULL` 的数据
- 列表为空返回 `{ "items": [] }`（可带 `total: 0`），不要 404
- 详情找不到或不是本人：`404`
- 日期字段：`YYYY-MM-DD`；时间字段：ISO 8601 UTC
- 两个列表接口前端用 `Promise.allSettled`：一边失败另一边仍展示
- **不要**做 `GET /timeline`；**不要**把就诊写入 `health_reports` 或把体检写入 `medical_archives`
- 拍照 OCR 只调 `POST /archives/ocr`：后端会分类并入库；成功后刷新两个列表即可

`GET /report-glossaries` 前端不调用。术语请内嵌在 `GET /health-reports/{id}` 的 `glossary`。

---

### 2.4.1 健康问题总结（档案首页卡片）

对应表：`health_summaries` + `health_summary_items`

#### `GET /health-summaries`（需登录）

按 `updated_at` 倒序返回当前用户的总结列表；每条带 `items`（按 `sort_order ASC`）。

`exam_date`、`exam_no`、`severity` 均可为 `null`。

响应：

```json
{
  "items": [
    {
      "id": "hs_xxx",
      "title": "健康问题总结",
      "exam_date": "2025-11-03",
      "exam_no": "312101033225",
      "summary_text": "综合近期体检与就诊记录……",
      "items": [
        {
          "id": "hsi_1",
          "content": "体重指数偏低（BMI 18.2），需加强营养与适量运动",
          "severity": "medium",
          "sort_order": 0
        }
      ],
      "created_at": "2026-07-29T04:02:00Z",
      "updated_at": "2026-07-29T04:02:00Z"
    }
  ]
}
```

前端：第一条含 `items` 的记录展示为「健康问题总结」主卡片；其余展示为普通总结卡片。

---

### 2.4.2 健康档案报告（体检时间轴 / 详情）

对应表：`health_reports` + `health_report_findings`；术语来自 `report_glossaries`（全局，无 `user_id`）

前端时间轴会把本列表与 `GET /archives` **合并后按日期倒序**。本接口只返回体检。

#### `GET /health-reports`（需登录）

| 参数 | 说明 |
|------|------|
| `page` | 默认 1 |
| `page_size` | 默认 20，最大 100；前端展示页传 `100` |

`ORDER BY exam_date DESC, created_at DESC`。  
列表**不要**带 `findings` / `full_text` / `glossary`。

```json
{
  "items": [
    {
      "id": "hr_xxx",
      "patient_name": "毕小雪",
      "exam_date": "2025-11-03",
      "org_name": "瑞慈体检上海静安机构",
      "voucher_no": "312101033225",
      "report_type": "体检报告"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 100
}
```

#### `GET /health-reports/{id}`（需登录）

`findings` 按 `sort_order ASC`。  
`full_text` 从 `health_reports.raw_payload.full_text` 取出（不要把整份 JSON 返回前端）；没有则 `null`，前端用占位文案。  
`glossary`：**请内嵌返回**（`report_glossaries WHERE enabled = 1 ORDER BY sort_order`）。

```json
{
  "id": "hr_xxx",
  "patient_name": "毕小雪",
  "exam_date": "2025-11-03",
  "org_name": "瑞慈体检上海静安机构",
  "voucher_no": "312101033225",
  "report_type": "体检报告",
  "findings": [
    {
      "id": "hrf_1",
      "title": "【1】体重过低。体重指数 BMI 值偏低（18.2）。",
      "suggestion": "建议平衡膳食，适量运动，定期复查体重。",
      "risk_level": "medium",
      "sort_order": 0
    }
  ],
  "full_text": "完整报告正文……",
  "glossary": [
    {
      "id": "g1",
      "term": "随诊",
      "definition": "如有不适，及时就诊。",
      "sort_order": 0
    }
  ]
}
```

#### `GET /report-glossaries`（需登录，可选）

前端展示页不调用。若已在报告详情内嵌 `glossary`，本接口可暂缓。

```json
{
  "items": [
    {"id": "g1", "term": "随诊", "definition": "如有不适，及时就诊。", "sort_order": 0}
  ]
}
```

---

### 2.4 档案 Archives（就诊单列表 / OCR）

对应表：`medical_archives`、`archive_ocr_jobs`（识别中间态）、体检写入 `health_reports`

展示页只读 `GET /archives`、`GET /archives/{id}`。  
**拍照/相册识别请只调 `POST /archives/ocr`**（后端分类并入库）。`POST /archives` 仅用于用户手工补录就诊单，不要在 OCR 成功后再用同一张单去创建。

#### `POST /archives/ocr`（需登录，`multipart/form-data`）

前端传一张图即可。后端用视觉模型判断类型并**立刻写入对应表**，返回已落库的 `id`。

| 字段 | 说明 |
|------|------|
| `file` | 图片，jpg / png / webp / gif，建议不超过 10MB |
| `source` | `camera` \| `album` |

建议超时 **≥ 60s**（识图比普通接口慢）。`config/api.json` 的 `timeoutMs` 若仍是 `30000`，OCR 请求请单独加长。

识别规则：

| `document_type` | 含义 | 写入表 | 返回的 `id` | 之后读哪个接口 |
|-----------------|------|--------|-------------|----------------|
| `visit` | 就诊单 / 处方 / 病历 / 出院小结 | `medical_archives` | 就诊单 id | `GET /archives`、`GET /archives/{id}` |
| `exam` | 体检报告 / 健康体检 | `health_reports` + findings | 体检报告 id | `GET /health-reports`、`GET /health-reports/{id}` |

前端流程：

1. `POST /archives/ocr`（`file` + `source`）
2. 看 `document_type` + `id` 决定跳转详情或刷新时间轴
3. **不要**再 `POST /archives` 把本次结果存一遍（同一 `visit_no` / `voucher_no` 会 `409`）
4. 时间轴仍用 `Promise.allSettled` 拉 `GET /health-reports` + `GET /archives`

响应字段（两种类型同一 JSON 形状；就诊单时体检字段为 `null` / `[]`）：

| 字段 | 就诊单 `visit` | 体检单 `exam` |
|------|----------------|---------------|
| `document_type` | `"visit"` | `"exam"` |
| `id` | 就诊单 id | 体检报告 id |
| `diagnosis` | 诊断白话 | 首条异常标题（兼容旧字段） |
| `medicine` | 用药/医嘱白话 | 多为「见体检建议」 |
| `visit_date` | 就诊日 `YYYY-MM-DD` | 等于 `exam_date` |
| `visit_no` | 就诊号 | 等于 `voucher_no` |
| `raw_ocr_text` | 全文 | 全文（详情 `full_text` 同源） |
| `patient_name` | `null` | 姓名 |
| `org_name` | `null` | 机构 |
| `voucher_no` | `null` | 体检凭证号 |
| `report_type` | `null` | 如「体检报告」 |
| `findings` | `[]` | 异常项列表 |

就诊单 `200` 示例：

```json
{
  "document_type": "visit",
  "id": "arc_xxx",
  "diagnosis": "支气管炎倾向，建议复查",
  "medicine": "按医嘱服用止咳药，注意饮水",
  "visit_date": "2026-07-27",
  "visit_no": "MZ202607270018",
  "raw_ocr_text": "原始 OCR 全文……",
  "patient_name": null,
  "org_name": null,
  "voucher_no": null,
  "report_type": null,
  "findings": []
}
```

体检单 `200` 示例：

```json
{
  "document_type": "exam",
  "id": "hr_xxx",
  "diagnosis": "体重过低 BMI 18.2",
  "medicine": "见体检建议",
  "visit_date": "2025-11-03",
  "visit_no": "312101033225",
  "raw_ocr_text": "完整报告正文……",
  "patient_name": "毕小雪",
  "org_name": "瑞慈体检上海静安机构",
  "voucher_no": "312101033225",
  "report_type": "体检报告",
  "findings": [
    {
      "title": "体重过低 BMI 18.2",
      "suggestion": "建议平衡膳食，适量运动，定期复查体重。",
      "risk_level": "medium",
      "sort_order": 0
    }
  ]
}
```

`findings[].risk_level`：`low` \| `medium` \| `high`，可 `null`。OCR 返回的 findings **没有** `id`；详情 `GET /health-reports/{id}` 才有 `id`。

错误：

| HTTP | `code` | 何时 |
|------|--------|------|
| 400 | `empty_file` | 空文件 |
| 400 | `image_too_large` | 超过约 10MB |
| 400 | `unsupported_image_type` | 非 jpg/png/webp/gif |
| 401 | （未登录） | 缺 token / token 无效 |
| 409 | `visit_no_conflict` | 该就诊号已存在 |
| 409 | `voucher_no_conflict` | 该体检凭证号已存在 |
| 422 | `invalid_source` | `source` 不是 camera/album |
| 502 | `ocr_invalid_json` / `ocr_empty_response` / `openai_upstream_error` | 模型识别失败 |

`409` 时识别可能已成功但未写入（号冲突）。前端提示「该单已在档案中」并刷新列表即可，不要换号强行再存同一张图。

---

#### `GET /archives`（需登录）

就诊单列表。前端与 `GET /health-reports` 合并成「健康档案报告」时间轴。  
时间轴卡片会用到：`diagnosis`、`medicine`、`visit_date`、`visit_no`。

`ORDER BY visit_date DESC, created_at DESC`。

查询参数：

| 参数 | 说明 |
|------|------|
| `q` | 关键词搜索；前端展示页不传，可暂缓 |
| `page` | 默认 1 |
| `page_size` | 默认 20，最大 100；前端展示页传 `100` |

响应：

```json
{
  "items": [ /* ArchiveRecord */ ],
  "total": 2,
  "page": 1,
  "page_size": 100
}
```

`ArchiveRecord`：

```json
{
  "id": "arc_xxx",
  "diagnosis": "...",
  "medicine": "...",
  "visit_date": "2026-07-27",
  "visit_no": "MZ202607270018",
  "raw_ocr_text": "...",
  "image_url": "https://...",
  "created_at": "2026-07-29T04:02:00Z",
  "updated_at": "2026-07-29T04:02:00Z"
}
```

列表里 `raw_ocr_text` / `image_url` 可空；详情接口必须能返回 `raw_ocr_text`（没有则 `null`）。

---

#### `POST /archives`（需登录）

**手工补录就诊单**（不是 OCR 成功后的下一步）。同一用户下 `visit_no` 未删除时唯一。  
不要用来保存体检单。

```json
{
  "diagnosis": "...",
  "medicine": "...",
  "visit_date": "2026-07-27",
  "visit_no": "MZ202607270018",
  "raw_ocr_text": "可选",
  "image_url": "可选"
}
```

响应：`201` + `ArchiveRecord`

---

#### `GET /archives/{id}`（需登录）

就诊单详情。前端「完整报告」Tab 使用 `raw_ocr_text`。校验所属用户，否则 `404`。

响应：`200` + `ArchiveRecord`（同上）。

#### `PATCH /archives/{id}`（需登录）

```json
{ "diagnosis": "...", "medicine": "...", "visit_date": "2026-07-27", "visit_no": "MZ202607270018" }
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

档案页展示接口可直接参考：

```text
docs/backend/archive_routes_example.py   # 已有总结/体检；就诊 GET /archives 需按契约补
docs/database/seed_archive.sql
docs/backend/README.md
docs/openapi.yaml                        # 已含 health-summaries / health-reports / archives
```

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
| 档案 OCR（拍照/相册） | **只调** `POST /archives/ocr`（`file`+`source`）。`visit`→就诊表，`exam`→体检表；用返回的 `id` 进详情。不要再 `POST /archives` |
| 档案首页总结 | `GET /health-summaries`（表 `health_summaries` / `health_summary_items`） |
| 健康档案报告时间轴 | 前端合并 `GET /health-reports` + `GET /archives`（不要单独做 timeline 接口） |
| 体检详情 | `GET /health-reports/{id}`（`findings` + `full_text` + 内嵌 `glossary`） |
| 就诊详情 | `GET /archives/{id}`（`raw_ocr_text` 作完整报告） |
| 报告术语 | 详情内嵌 `glossary`；`GET /report-glossaries` 可选 |
| 推送子女 / 导出（可后做） | `POST /archives/{id}/share`、`GET /archives/{id}/export` |
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
