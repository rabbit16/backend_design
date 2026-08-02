# 数据库设计说明：为什么这样建表、怎么用

面向「适老化语音问答 App」。  
配套文件：[`schema.sql`](./schema.sql) · [`er.mmd`](./er.mmd) · 接口 [`../API.md`](../API.md)

---

## 1. 设计目标

| 目标 | 做法 |
|------|------|
| 跟前端页面一一对应 | 登录 / 问询 / 档案 / 个人中心各有独立表簇 |
| 跟 API 契约对齐 | 字段名尽量贴近 `docs/API.md` 的 JSON |
| 老人端操作简单 | 后端可复杂，表结构支持「少步骤、可回看、可推给子女」 |
| 可演进 | 媒体统一落库；偏好/规则独立表，方便加字体、对比度等 |

---

## 2. 总体约定

1. **主键**：`CHAR(36)` UUID，应用层生成（ORM：`new_uuid()`）。
2. **时间**：`DATETIME(6)`，约定存 **UTC**；接口输出 ISO8601。
3. **软删除**：业务主数据用 `deleted_at`；查询默认 `deleted_at IS NULL`。
4. **密码可空**：支持「验证码注册 → 稍后设密」。
5. **媒体不散落**：语音、病历图、PDF 都先记 `media_files`，业务表只存 `*_media_id`。
6. **MySQL 8**：InnoDB + utf8mb4；JSON 用 `JSON`；布尔用 `TINYINT(1)`。

---

## 3. 模块怎么拆（一句话）

```text
认证身份 ──► 问询过程 ──► 档案沉淀 ──► 家属协同
   │            │            │            │
 users       qa_*        medical_*     family_*
 sms/session  voice_*     health_*      archive_shares
             media_files  media_files
```

- **认证**：谁能登录、token 怎么失效  
- **问询**：一次「说话/打字 → 得到回答 → 可选就医建议」  
- **档案**：就诊单 OCR、健康总结、体检报告时间轴  
- **家属**：联系人 + 推送规则 + 把档案推出去 / 导出 PDF  

---

## 4. 按页面：这些表怎么用

### 4.1 登录页

| 用户动作 | 用到的表 | 说明 |
|----------|----------|------|
| 获取验证码 | `sms_codes` | 写入手机号、验证码、过期时间；限流看同一手机最近发送 |
| 验证码登录 | `sms_codes` → `users` → `auth_sessions` | 校验码；没有用户则注册；签发 access/refresh，refresh **哈希**写入会话 |
| 密码登录 | `users` | 校验 `password_hash`；同样写 `auth_sessions` |
| 退出 | `auth_sessions` | `revoked_at` 置值，refresh 失效 |
| 刷新 token | `auth_sessions` | 校验未撤销的 refresh，轮换会话 |

**为什么拆 `sms_codes` / `auth_sessions`？**  
验证码是短生命周期、可审计；会话负责 logout / 多端踢下线，不把 refresh 明文存库。

对应接口：`POST /auth/sms/send`、`/auth/login/sms`、`/auth/login/password`、`/auth/logout`、`/auth/token/refresh`。

---

### 4.2 个人中心

| 能力 | 表 | 用法 |
|------|----|------|
| 资料 | `users` | `display_name`、`phone`、`preferred_lang` |
| 语言/字体等偏好 | `user_preferences` | 与 `users` 1:1；预留 `font_scale`、`high_contrast` |
| 改密码 | `users.password_hash` | 已有密码需校验旧密码 |
| 家属列表 | `family_contacts` | 女儿/儿子/自定义；软删除 |
| 推送开关 | `family_push_rules` | 与用户 1:1：`on_record_saved` / `on_abnormal` / `on_visit` |

**为什么偏好单独表？**  
账号安全字段（密码、状态）和 UI 偏好生命周期不同，扩展设置页时不必动 `users`。

对应接口：`GET /me`、`/me/preferences`、`/family/contacts`、`/family/rules`、`POST /auth/password`。

---

### 4.3 首页问询（按住说话 / 文字 · 多轮对话）

**适老化文字输入（推荐）**：前端只调 `POST /qa/ask`，**不传 session_id**。

```text
Redis key: qa:context:user:{user_id}  →  context_id(=qa_sessions.id)
TTL: 默认 2592000 秒（30 天），自创建起固定过期；期内提问不续期

流程：
  1. 从 Redis 取未过期 context_id
  2. 命中 → 加载 qa_sessions + qa_messages 作为上下文，追加本轮（不刷新 TTL）
  3. 未命中/过期 → 新建 qa_sessions，写入 Redis（此时才设置 30 天 TTL），再对话
  4. 落库 qa_messages（user / assistant）
```

`REDIS_ENABLED=false` 时用进程内存缓存（重启丢失，仅开发/单测）。

**显式会话 API**（可选）：

```text
首轮：POST /qa/sessions
追问：POST /qa/sessions/{session_id}/messages
列表/回看：GET /qa/sessions、GET /qa/sessions/{id}
```

| 表 | 何时写 | 读什么 |
|----|--------|--------|
| `media_files` | 收到音频时 | `kind=audio` |
| `voice_recognize_jobs` | `POST /voice/recognize` | 识别文本；可挂到本轮 `qa_messages.voice_job_id` |
| `qa_sessions` | 开新对话时 | `id` 即 session_id；`title`/`message_count`/`last_message_at` 方便列表 |
| `qa_messages` | 每一轮用户问、助手答 | `role` + `content` + `turn_index`；还原多轮历史 |
| `qa_recommendations` | 点「医疗推荐」 | 基于**整段会话**上下文生成；与 session 1:1 |

**文字模式**：`input_mode=text` 写在对应的 **user** 消息上，可不建 `voice_recognize_jobs`。

**为何拆会话 / 消息？**

| 需求 | 做法 |
|------|------|
| 每个会话唯一 ID | `qa_sessions.id` |
| 保留老人追问记录 | 多行 `qa_messages`，不可覆盖历史 |
| 给大模型喂上下文 | `WHERE session_id=? ORDER BY turn_index` |
| 会话列表页 | 只扫 `qa_sessions`（看 title / last_message_at），不必扫全部消息 |

---

### 4.4 档案页 · 识别就诊单

```text
拍照/相册 → media_files (image)
     ↓
OCR 临时结果 → archive_ocr_jobs
     ↓
用户确认保存 → medical_archives
```

| 表 | 角色 |
|----|------|
| `archive_ocr_jobs` | 识别中间态：可失败、可重试；**未保存也可查** |
| `medical_archives` | 用户确认后的正式档案：诊断、用药、就诊日；列表时间线 |

**为什么 OCR 任务和正式档案分开？**  
避免「识别错了但已经进档案」；保存前可编辑再 `POST /archives`。

推送 / 导出：

| 动作 | 表 |
|------|----|
| 推送给子女 | `archive_shares` → 指向 `family_contacts`；状态 queued/sent/failed |
| 导出 PDF | `archive_exports` + 可选 `media_files`；返回带过期的 `download_url` |

推送前应看 `family_push_rules`（例如仅在「就诊单保存后」开启时自动推）。

---

### 4.5 档案页 · 健康问题总结

| 表 | 用法 |
|----|------|
| `health_summaries` | 一块「总述」卡片：标题、最近检查日、检查号、总结正文 |
| `health_summary_items` | 总述下的多条问题（如「体重指数偏低…」），带 `sort_order` |

适合「把多条就诊/体检揉成一段老人能看懂的话」；与单张就诊单 `medical_archives` 互补，不互相替代。

---

### 4.6 档案页 · 健康档案报告（时间轴）

| 表 | 用法 |
|----|------|
| `health_reports` | 时间轴卡片：姓名、日期、机构、凭证号、类型徽章 |
| `health_report_findings` | 详情里「异常结果与建议」列表 |
| `report_glossaries` | **全局**术语（随诊/诊治/复查），不按用户 |

**和就诊单的区别：**

| | `medical_archives` | `health_reports` |
|--|--------------------|------------------|
| 来源 | 就诊单 OCR | 体检/健康档案报告 |
| 列表形态 | 档案时间线（就诊） | 报告查询时间轴 |
| 详情重点 | 诊断 + 用药 | 异常项 + 建议 + 术语 |

未删除时 `(user_id, voucher_no)` 唯一（MySQL 用生成列 `active_voucher` 实现）。

---

## 5. 核心关系（读图用）

```text
users
 ├─ 1:1  user_preferences / family_push_rules
 ├─ 1:N  auth_sessions / media_files / family_contacts
 ├─ 1:N  qa_sessions ──1:N── qa_messages
 │            └──1:1── qa_recommendations
 ├─ 1:N  medical_archives ──N── archive_shares → family_contacts
 │                      └──N── archive_exports → media_files
 ├─ 1:N  health_summaries ──N── health_summary_items
 └─ 1:N  health_reports ──N── health_report_findings

media_files ← 被语音、OCR、报告 PDF、导出 PDF、消息音频 多处引用
report_glossaries ← 全局配置，无 user_id
audit_logs ← 可选，不参与主业务外键
```

ER 图（中文，可导入 draw.io）：[`er.mmd`](./er.mmd)

---

## 6. 典型业务时序（实现后端时照此写）

### 验证码登录

1. 写 `sms_codes`  
2. 校验码 → upsert `users`  
3. 写 `auth_sessions`（refresh hash）  
4. 返回 JWT + `UserProfile`

### 语音问询 + 多轮追问 + 就医建议

1. 存音频 → `media_files`；识别 → `voice_recognize_jobs`  
2. 首轮：建 `qa_sessions`，写 2 条 `qa_messages`（user / assistant）  
3. 追问：同一 `session_id` 继续追加 `qa_messages`；加载历史再调模型  
4. 可选：基于整段会话写/更新 `qa_recommendations`

### 就诊单 OCR 保存并推送

1. 图片 → `media_files`  
2. OCR → `archive_ocr_jobs`  
3. 保存 → `medical_archives`  
4. 若规则允许 → 按联系人批量写 `archive_shares`

---

## 7. 故意不做的事（避免过度设计）

| 不做 | 原因 |
|------|------|
| 把问答和档案塞一张「万能 timeline」 | 页面形态不同，先分表；以后可用视图合并 |
| refresh 明文入库 | 泄露面太大，只存哈希 |
| OCR 直接覆盖正式档案 | 老人会改字，需要确认步 |
| 术语表挂在用户下 | 文案全局一致，用 `report_glossaries` |

---

## 8. 改表时建议同步

1. `docs/database/schema.sql`  
2. `src/app/db/models/*` + Alembic 迁移  
3. `docs/API.md` / `openapi.yaml`（若接口字段变了）  
4. 本文件的「页面用法」小节（避免后人只看表名猜错）

---

## 9. 和代码目录的对应

| 表簇 | ORM |
|------|-----|
| 用户/会话/偏好 | `src/app/db/models/user.py` |
| 媒体 | `media.py` |
| 问询 | `qa.py`（`QaSession` / `QaMessage` / `QaRecommendation` / `VoiceRecognizeJob`） |
| 就诊档案/推送导出 | `archive.py` |
| 健康总结/报告 | `health.py` |
| 家属 | `family.py` |
| 审计 | `audit.py` |
