# 数据库表结构说明（MySQL 8.0+）

对应 SQL：[`schema.sql`](./schema.sql)  
对应 ER 图（中文 Mermaid，可导入 draw.io）：[`er.mmd`](./er.mmd)  
对应设计与用法说明：[`DESIGN.md`](./DESIGN.md)  
对应接口：[`../API.md`](../API.md)

可直接改 `schema.sql` 字段；改完后建议同步接口文档与 ORM（`src/app/db/models/`）。

## 模块一览

| 模块 | 表 | 对应页面/能力 |
|------|----|----------------|
| 用户认证 | `users` `sms_codes` `auth_sessions` `user_preferences` | 登录、退出、改密、个人资料 |
| 媒体 | `media_files` | 语音、病历图、PDF |
| 问询（多轮） | `voice_recognize_jobs` `qa_sessions` `qa_messages` `qa_recommendations` | 语音/文字问询、对话历史、就医推荐 |
| 就诊档案 | `medical_archives` `archive_ocr_jobs` | 识别就诊单、保存档案 |
| 健康总结 | `health_summaries` `health_summary_items` | 档案页「健康问题总结」 |
| 健康报告 | `health_reports` `health_report_findings` `report_glossaries` | 「健康档案报告」列表/详情 |
| 推送导出 | `archive_shares` `archive_exports` | 推送子女、导出 PDF |
| 家属 | `family_contacts` `family_push_rules` | 个人中心联系人与规则 |
| 审计（可选） | `audit_logs` | 联调排障 |

## ER 关系（简图）

```text
users
 ├─ user_preferences (1:1)
 ├─ auth_sessions (1:N)
 ├─ family_contacts (1:N)
 ├─ family_push_rules (1:1)
 ├─ media_files (1:N)
 ├─ qa_sessions (1:N)
 │    ├─ qa_messages (1:N)          ← 多轮对话记录
 │    └─ qa_recommendations (1:1)
 ├─ medical_archives (1:N)
 │    ├─ archive_shares → family_contacts
 │    └─ archive_exports → media_files
 ├─ health_summaries (1:N)
 │    └─ health_summary_items (1:N)
 └─ health_reports (1:N)
      └─ health_report_findings (1:N)

report_glossaries （全局配置，不挂 user）
```

## MySQL 对照说明（相对原 PostgreSQL 草案）

| PostgreSQL | MySQL 8 |
|------------|---------|
| `UUID` + `gen_random_uuid()` | `CHAR(36)`，应用层生成 UUID（或 `DEFAULT (UUID())`） |
| `TIMESTAMPTZ` | `DATETIME(6)`（应用约定存 UTC） |
| `BOOLEAN` | `TINYINT(1)` |
| `JSONB` | `JSON` |
| `BIGSERIAL` | `BIGINT AUTO_INCREMENT` |
| 部分唯一索引 `WHERE deleted_at IS NULL` | 生成列 `active_voucher` + 唯一键 |
| `COMMENT ON ...` | 列/表 `COMMENT='...'` |

## 导入 draw.io（推荐 Mermaid）

1. 打开 [diagrams.net](https://app.diagrams.net/) 或桌面版 draw.io
2. **排列 → 插入 → 高级 → Mermaid…**
3. 打开 [`er.mmd`](./er.mmd)，全选复制（从 `erDiagram` 起，不要带代码围栏）
4. 粘贴后点 **插入**

表意说明、页面用法、业务时序见 [`DESIGN.md`](./DESIGN.md)。

## 本地建库示例

```bash
mysql -u root -p -e "CREATE DATABASE senior_voice DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -u root -p senior_voice < docs/database/schema.sql
```

后端连接串（`.env`）：

```env
DATABASE_URL=mysql+aiomysql://user:password@localhost:3306/senior_voice?charset=utf8mb4
```

迁移：

```bash
PYTHONPATH=. python scripts/db_migrate.py upgrade
```

## 修改建议

1. **主键**：当前 `CHAR(36)` UUID；若团队更熟自增，可改 `BIGINT AUTO_INCREMENT`。
2. **报告与就诊单**：`medical_archives`=就诊单 OCR，`health_reports`=体检报告时间轴；若要统一时间线可加 `timeline_events`。
3. **密码可空**：支持「仅验证码注册、稍后设密」。
4. **软删除**：业务表带 `deleted_at`，物理删除慎用。
