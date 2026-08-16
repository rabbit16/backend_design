-- =============================================================================
-- 适老化语音问答 App · 数据库表结构（MySQL 8.0+）
-- =============================================================================
-- 依据：前端页面（登录 / 问询 / 档案 / 个人）+ docs/API.md / openapi.yaml
-- 引擎：MySQL 8.0+ / InnoDB / utf8mb4
-- 约定：
--   1. 主键 CHAR(36) UUID（应用层生成，或 DEFAULT (UUID())）
--   2. 时间存 UTC（DATETIME(6)），应用层用 ISO8601 输出
--   3. 软删除用 deleted_at；业务查询默认加 deleted_at IS NULL
--   4. JSONB → JSON；BOOLEAN → TINYINT(1)；CHECK 需 MySQL 8.0.16+
-- =============================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- -----------------------------------------------------------------------------
-- 1. 用户与认证（登录页 / 个人中心）
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id              CHAR(36)     NOT NULL,
    phone           VARCHAR(20)  NOT NULL COMMENT '登录手机号，唯一',
    password_hash   VARCHAR(255) NULL COMMENT 'bcrypt/argon2 哈希；可为空（仅验证码注册）',
    display_name    VARCHAR(64)  NULL COMMENT '展示名',
    preferred_lang  VARCHAR(8)   NOT NULL DEFAULT 'zh' COMMENT 'zh | en',
    status          VARCHAR(16)  NOT NULL DEFAULT 'active' COMMENT 'active | disabled',
    created_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    deleted_at      DATETIME(6)  NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_phone (phone),
    CONSTRAINT ck_users_lang CHECK (preferred_lang IN ('zh', 'en')),
    CONSTRAINT ck_users_status CHECK (status IN ('active', 'disabled'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='用户：登录、个人中心账号信息';

CREATE TABLE IF NOT EXISTS sms_codes (
    id           CHAR(36)     NOT NULL,
    phone        VARCHAR(20)  NOT NULL,
    code         VARCHAR(8)   NOT NULL,
    purpose      VARCHAR(32)  NOT NULL DEFAULT 'login' COMMENT 'login | register | reset_password',
    expires_at   DATETIME(6)  NOT NULL,
    used_at      DATETIME(6)  NULL,
    request_ip   VARCHAR(64)  NULL,
    created_at   DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_sms_codes_phone_created (phone, created_at),
    CONSTRAINT ck_sms_purpose CHECK (purpose IN ('login', 'register', 'reset_password'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='短信验证码：POST /auth/sms/send、/auth/login/sms';

CREATE TABLE IF NOT EXISTS auth_sessions (
    id                 CHAR(36)     NOT NULL,
    user_id            CHAR(36)     NOT NULL,
    refresh_token_hash VARCHAR(128) NOT NULL COMMENT '只存 hash，不存明文',
    device_info        VARCHAR(255) NULL,
    expires_at         DATETIME(6)  NOT NULL,
    revoked_at         DATETIME(6)  NULL COMMENT '退出登录时置值',
    created_at         DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_auth_sessions_refresh (refresh_token_hash),
    KEY idx_auth_sessions_user (user_id),
    CONSTRAINT fk_auth_sessions_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='登录会话：签发/刷新/注销 access+refresh token';

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id         CHAR(36)     NOT NULL,
    preferred_lang  VARCHAR(8)   NOT NULL DEFAULT 'zh',
    font_scale      DECIMAL(3,2) NOT NULL DEFAULT 1.00 COMMENT '预留：字体缩放',
    high_contrast   TINYINT(1)   NOT NULL DEFAULT 0 COMMENT '预留：高对比',
    updated_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (user_id),
    CONSTRAINT fk_user_preferences_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT ck_pref_lang CHECK (preferred_lang IN ('zh', 'en'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='个人偏好：GET/PATCH /me/preferences';

-- -----------------------------------------------------------------------------
-- 2. 媒体文件（语音、病历图片、导出 PDF）
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS media_files (
    id            CHAR(36)      NOT NULL,
    user_id       CHAR(36)      NOT NULL,
    kind          VARCHAR(32)   NOT NULL COMMENT 'audio | image | pdf | other',
    mime_type     VARCHAR(128)  NOT NULL,
    storage_key   VARCHAR(512)  NOT NULL COMMENT '对象存储路径或本地路径',
    url           VARCHAR(1024) NULL COMMENT '可访问 URL（可签名）',
    size_bytes    BIGINT        NULL,
    checksum      VARCHAR(64)   NULL,
    created_at    DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    deleted_at    DATETIME(6)   NULL,
    PRIMARY KEY (id),
    KEY idx_media_files_user (user_id, created_at),
    CONSTRAINT fk_media_files_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT ck_media_kind CHECK (kind IN ('audio', 'image', 'pdf', 'other'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='上传文件元数据：语音识别、OCR、PDF 导出共用';

-- -----------------------------------------------------------------------------
-- 3. 问询（首页：语音 / 文字 → 问答 → 就医推荐）
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS voice_recognize_jobs (
    id              CHAR(36)     NOT NULL,
    user_id         CHAR(36)     NOT NULL,
    media_id        CHAR(36)     NULL,
    lang            VARCHAR(8)   NOT NULL DEFAULT 'zh',
    recognized_text TEXT         NULL,
    duration_ms     INT          NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'succeeded' COMMENT 'pending | succeeded | failed',
    error_message   TEXT         NULL,
    created_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_voice_jobs_user (user_id, created_at),
    CONSTRAINT fk_voice_jobs_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_voice_jobs_media FOREIGN KEY (media_id) REFERENCES media_files (id),
    CONSTRAINT ck_voice_lang CHECK (lang IN ('zh', 'en')),
    CONSTRAINT ck_voice_status CHECK (status IN ('pending', 'succeeded', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='语音识别：POST /voice/recognize';

-- 多轮对话：会话容器（每个会话唯一 session_id）
CREATE TABLE IF NOT EXISTS qa_sessions (
    id                CHAR(36)     NOT NULL COMMENT '会话唯一ID',
    user_id           CHAR(36)     NOT NULL,
    lang              VARCHAR(8)   NOT NULL DEFAULT 'zh',
    title             VARCHAR(128) NULL COMMENT '会话标题，默认取首问截断',
    status            VARCHAR(16)  NOT NULL DEFAULT 'active' COMMENT 'active | closed',
    message_count     INT          NOT NULL DEFAULT 0 COMMENT '消息条数（含用户与助手）',
    last_message_at   DATETIME(6)  NULL COMMENT '最近一条消息时间，便于列表排序',
    created_at        DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at        DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    deleted_at        DATETIME(6)  NULL,
    PRIMARY KEY (id),
    KEY idx_qa_sessions_user (user_id, last_message_at),
    CONSTRAINT fk_qa_sessions_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT ck_qa_lang CHECK (lang IN ('zh', 'en')),
    CONSTRAINT ck_qa_session_status CHECK (status IN ('active', 'closed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='问询多轮会话：一次老人连续追问共用一个 session_id';

-- 多轮对话：会话内每条消息（用户问 / 助手答）
CREATE TABLE IF NOT EXISTS qa_messages (
    id              CHAR(36)     NOT NULL,
    session_id      CHAR(36)     NOT NULL COMMENT '所属会话',
    user_id         CHAR(36)     NOT NULL COMMENT '冗余用户ID，便于按人查询',
    turn_index      INT          NOT NULL COMMENT '会话内序号，从1递增',
    role            VARCHAR(16)  NOT NULL COMMENT 'user | assistant | system',
    content         TEXT         NOT NULL COMMENT '文本内容',
    input_mode      VARCHAR(16)  NULL COMMENT 'voice | text；仅 user 轮有意义',
    audio_media_id  CHAR(36)     NULL COMMENT '本轮语音文件',
    voice_job_id    CHAR(36)     NULL COMMENT '本轮语音识别任务',
    created_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_qa_messages_session_turn (session_id, turn_index),
    KEY idx_qa_messages_session (session_id, turn_index),
    KEY idx_qa_messages_user (user_id, created_at),
    CONSTRAINT fk_qa_messages_session FOREIGN KEY (session_id) REFERENCES qa_sessions (id) ON DELETE CASCADE,
    CONSTRAINT fk_qa_messages_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_qa_messages_audio FOREIGN KEY (audio_media_id) REFERENCES media_files (id),
    CONSTRAINT fk_qa_messages_voice_job FOREIGN KEY (voice_job_id) REFERENCES voice_recognize_jobs (id),
    CONSTRAINT ck_qa_msg_role CHECK (role IN ('user', 'assistant', 'system')),
    CONSTRAINT ck_qa_msg_input_mode CHECK (input_mode IS NULL OR input_mode IN ('voice', 'text'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='问询消息：按 turn_index 还原多轮上下文';

CREATE TABLE IF NOT EXISTS qa_recommendations (
    id            CHAR(36)     NOT NULL,
    session_id    CHAR(36)     NOT NULL COMMENT '基于整个会话上下文生成',
    user_id       CHAR(36)     NOT NULL,
    title         VARCHAR(128) NOT NULL,
    body          TEXT         NOT NULL,
    risk_level    VARCHAR(16)  NOT NULL DEFAULT 'low' COMMENT 'low | medium | high',
    disclaimer    TEXT         NOT NULL,
    created_at    DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    UNIQUE KEY uq_qa_recommendations_session (session_id),
    KEY idx_qa_recommendations_user (user_id),
    CONSTRAINT fk_qa_reco_session FOREIGN KEY (session_id) REFERENCES qa_sessions (id) ON DELETE CASCADE,
    CONSTRAINT fk_qa_reco_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT ck_risk CHECK (risk_level IN ('low', 'medium', 'high'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='就医推荐：POST /qa/sessions/{id}/recommendations';

-- -----------------------------------------------------------------------------
-- 4. 档案（识别就诊单 / 健康问题总结 / 健康档案报告）
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS medical_archives (
    id             CHAR(36)     NOT NULL,
    user_id        CHAR(36)     NOT NULL,
    diagnosis      TEXT         NOT NULL COMMENT '诊断',
    medicine       TEXT         NOT NULL COMMENT '用药',
    visit_date     DATE         NOT NULL COMMENT '就诊/检查日期',
    visit_no       VARCHAR(64)  NOT NULL COMMENT '就诊号/门诊号',
    raw_ocr_text   TEXT         NULL,
    image_media_id CHAR(36)     NULL,
    source         VARCHAR(16)  NULL COMMENT 'camera | album',
    created_at     DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at     DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    deleted_at     DATETIME(6)  NULL,
    -- MySQL 无部分唯一索引：用生成列模拟「未删除时 user_id+visit_no 唯一」
    active_visit_no CHAR(64)    GENERATED ALWAYS AS (
        IF(deleted_at IS NULL, visit_no, NULL)
    ) STORED,
    PRIMARY KEY (id),
    KEY idx_medical_archives_user_date (user_id, visit_date),
    UNIQUE KEY uq_medical_archives_user_active_visit (user_id, active_visit_no),
    CONSTRAINT fk_medical_archives_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_medical_archives_image FOREIGN KEY (image_media_id) REFERENCES media_files (id),
    CONSTRAINT ck_archive_source CHECK (source IS NULL OR source IN ('camera', 'album'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='就诊单档案：GET/POST /archives，时间轴卡片用 diagnosis/medicine/visit_date/visit_no';

CREATE TABLE IF NOT EXISTS archive_ocr_jobs (
    id             CHAR(36)     NOT NULL,
    user_id        CHAR(36)     NOT NULL,
    image_media_id CHAR(36)     NULL,
    source         VARCHAR(16)  NOT NULL COMMENT 'camera | album',
    diagnosis      TEXT         NULL,
    medicine       TEXT         NULL,
    visit_date     DATE         NULL,
    visit_no       VARCHAR(64)  NULL COMMENT '识别出的就诊号',
    raw_ocr_text   TEXT         NULL,
    status         VARCHAR(16)  NOT NULL DEFAULT 'succeeded' COMMENT 'pending | succeeded | failed',
    created_at     DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_archive_ocr_jobs_user (user_id, created_at),
    CONSTRAINT fk_archive_ocr_jobs_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_archive_ocr_jobs_image FOREIGN KEY (image_media_id) REFERENCES media_files (id),
    CONSTRAINT ck_ocr_source CHECK (source IN ('camera', 'album')),
    CONSTRAINT ck_ocr_status CHECK (status IN ('pending', 'succeeded', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='OCR 任务：POST /archives/ocr';

CREATE TABLE IF NOT EXISTS health_summaries (
    id            CHAR(36)     NOT NULL,
    user_id       CHAR(36)     NOT NULL,
    title         VARCHAR(128) NOT NULL DEFAULT '健康问题总结',
    exam_date     DATE         NULL COMMENT '关联最近检查日期',
    exam_no       VARCHAR(64)  NULL COMMENT '检查号',
    summary_text  TEXT         NOT NULL COMMENT '总述文案',
    created_at    DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at    DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    deleted_at    DATETIME(6)  NULL,
    PRIMARY KEY (id),
    KEY idx_health_summaries_user (user_id, updated_at),
    CONSTRAINT fk_health_summaries_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='健康问题总结主表';

CREATE TABLE IF NOT EXISTS health_summary_items (
    id            CHAR(36)     NOT NULL,
    summary_id    CHAR(36)     NOT NULL,
    sort_order    INT          NOT NULL DEFAULT 0,
    content       TEXT         NOT NULL,
    severity      VARCHAR(16)  NULL COMMENT 'low | medium | high',
    created_at    DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_health_summary_items_summary (summary_id, sort_order),
    CONSTRAINT fk_health_summary_items_summary
        FOREIGN KEY (summary_id) REFERENCES health_summaries (id) ON DELETE CASCADE,
    CONSTRAINT ck_summary_item_sev CHECK (severity IS NULL OR severity IN ('low', 'medium', 'high'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='健康问题总结条目';

CREATE TABLE IF NOT EXISTS health_reports (
    id              CHAR(36)     NOT NULL,
    user_id         CHAR(36)     NOT NULL,
    patient_name    VARCHAR(64)  NOT NULL COMMENT '报告姓名',
    exam_date       DATE         NOT NULL,
    org_name        VARCHAR(128) NOT NULL COMMENT '机构名',
    voucher_no      VARCHAR(64)  NOT NULL COMMENT '检查凭证/检查号',
    report_type     VARCHAR(32)  NOT NULL DEFAULT '体检报告' COMMENT '徽章文案',
    pdf_media_id    CHAR(36)     NULL,
    raw_payload     JSON         NULL COMMENT '完整报告原始 JSON',
    -- MySQL 无部分唯一索引：用生成列模拟「未删除时 user_id+voucher_no 唯一」
    active_voucher  CHAR(64)     GENERATED ALWAYS AS (
        IF(deleted_at IS NULL, voucher_no, NULL)
    ) STORED,
    created_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at      DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    deleted_at      DATETIME(6)  NULL,
    PRIMARY KEY (id),
    KEY idx_health_reports_user_date (user_id, exam_date),
    UNIQUE KEY uq_health_reports_user_active_voucher (user_id, active_voucher),
    CONSTRAINT fk_health_reports_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_health_reports_pdf FOREIGN KEY (pdf_media_id) REFERENCES media_files (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='健康档案报告列表：报告查询页时间轴卡片';

CREATE TABLE IF NOT EXISTS health_report_findings (
    id             CHAR(36)     NOT NULL,
    report_id      CHAR(36)     NOT NULL,
    sort_order     INT          NOT NULL DEFAULT 0,
    title          TEXT         NOT NULL,
    suggestion     TEXT         NOT NULL,
    risk_level     VARCHAR(16)  NULL,
    created_at     DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_report_findings_report (report_id, sort_order),
    CONSTRAINT fk_report_findings_report
        FOREIGN KEY (report_id) REFERENCES health_reports (id) ON DELETE CASCADE,
    CONSTRAINT ck_finding_risk CHECK (risk_level IS NULL OR risk_level IN ('low', 'medium', 'high'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='报告异常项：详情 Tab「异常结果与建议」';

CREATE TABLE IF NOT EXISTS report_glossaries (
    id          CHAR(36)     NOT NULL,
    term        VARCHAR(64)  NOT NULL COMMENT '随诊 / 诊治 / 复查',
    definition  TEXT         NOT NULL,
    sort_order  INT          NOT NULL DEFAULT 0,
    enabled     TINYINT(1)   NOT NULL DEFAULT 1,
    created_at  DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='体检报告术语释义（全局配置，非按用户）';

CREATE TABLE IF NOT EXISTS family_contacts (
    id          CHAR(36)     NOT NULL,
    user_id     CHAR(36)     NOT NULL,
    name        VARCHAR(64)  NOT NULL COMMENT '女儿 / 儿子 / 自定义',
    phone       VARCHAR(20)  NOT NULL,
    relation    VARCHAR(32)  NULL COMMENT 'daughter | son | other',
    created_at  DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at  DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    deleted_at  DATETIME(6)  NULL,
    PRIMARY KEY (id),
    KEY idx_family_contacts_user (user_id),
    CONSTRAINT fk_family_contacts_user FOREIGN KEY (user_id) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='家属联系人：/family/contacts';

CREATE TABLE IF NOT EXISTS archive_shares (
    id            CHAR(36)     NOT NULL,
    archive_id    CHAR(36)     NOT NULL,
    user_id       CHAR(36)     NOT NULL,
    contact_id    CHAR(36)     NOT NULL,
    message       TEXT         NULL,
    status        VARCHAR(16)  NOT NULL DEFAULT 'queued' COMMENT 'queued | sent | failed',
    created_at    DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    sent_at       DATETIME(6)  NULL,
    PRIMARY KEY (id),
    KEY idx_archive_shares_archive (archive_id),
    CONSTRAINT fk_archive_shares_archive
        FOREIGN KEY (archive_id) REFERENCES medical_archives (id) ON DELETE CASCADE,
    CONSTRAINT fk_archive_shares_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_archive_shares_contact FOREIGN KEY (contact_id) REFERENCES family_contacts (id),
    CONSTRAINT ck_share_status CHECK (status IN ('queued', 'sent', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='推送子女：POST /archives/{id}/share';

CREATE TABLE IF NOT EXISTS archive_exports (
    id             CHAR(36)      NOT NULL,
    archive_id     CHAR(36)      NOT NULL,
    user_id        CHAR(36)      NOT NULL,
    pdf_media_id   CHAR(36)      NULL,
    download_url   VARCHAR(1024) NULL,
    expires_at     DATETIME(6)   NULL,
    status         VARCHAR(16)   NOT NULL DEFAULT 'ready' COMMENT 'pending | ready | failed',
    created_at     DATETIME(6)   NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_archive_exports_archive (archive_id),
    CONSTRAINT fk_archive_exports_archive
        FOREIGN KEY (archive_id) REFERENCES medical_archives (id) ON DELETE CASCADE,
    CONSTRAINT fk_archive_exports_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT fk_archive_exports_pdf FOREIGN KEY (pdf_media_id) REFERENCES media_files (id),
    CONSTRAINT ck_export_status CHECK (status IN ('pending', 'ready', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='导出 PDF：GET /archives/{id}/export';

CREATE TABLE IF NOT EXISTS family_push_rules (
    user_id           CHAR(36)    NOT NULL,
    on_record_saved   TINYINT(1)  NOT NULL DEFAULT 1 COMMENT '就诊单保存后推送',
    on_abnormal       TINYINT(1)  NOT NULL DEFAULT 0 COMMENT '异常指标提醒',
    on_visit          TINYINT(1)  NOT NULL DEFAULT 1 COMMENT '就诊复查提醒',
    updated_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (user_id),
    CONSTRAINT fk_family_push_rules_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='推送触发规则：GET/PUT /family/rules';

-- -----------------------------------------------------------------------------
-- 5. 可选：操作审计
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit_logs (
    id          BIGINT       NOT NULL AUTO_INCREMENT,
    user_id     CHAR(36)     NULL,
    action      VARCHAR(64)  NOT NULL COMMENT 'login | ocr | share | export ...',
    resource    VARCHAR(64)  NULL,
    resource_id CHAR(36)     NULL,
    detail      JSON         NULL,
    ip          VARCHAR(64)  NULL,
    created_at  DATETIME(6)  NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_audit_logs_user_time (user_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='可选审计日志，不强制接入业务';

SET FOREIGN_KEY_CHECKS = 1;

-- =============================================================================
-- 页面 ↔ 表 对照
-- =============================================================================
-- 登录页: users, sms_codes, auth_sessions
-- 问询页: voice_recognize_jobs, qa_sessions, qa_messages, qa_recommendations, media_files
-- 档案页: medical_archives, archive_ocr_jobs, health_summaries/items,
--         health_reports/findings, report_glossaries, archive_shares/exports
-- 个人中心: users, user_preferences, family_contacts, family_push_rules
-- =============================================================================
