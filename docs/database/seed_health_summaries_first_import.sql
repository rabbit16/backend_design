-- =============================================================================
-- 首次导入样例：仅「健康问题总结」
-- 场景：用户第一次有体检/档案数据，尚无「近期问题总结」「上次随访结果总结」
-- 表：health_summaries + health_summary_items
--
-- 使用前改 @user_id（或启用按手机号取值）
--   mysql -u... -p your_db < docs/database/seed_health_summaries_first_import.sql
-- =============================================================================

-- 与 schema（utf8mb4_unicode_ci）对齐，避免与连接默认 0900_ai_ci 混用报错
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

SET @user_id := '17491760-7308-46e5-8e8b-213ad9314b83' COLLATE utf8mb4_unicode_ci;
-- SET @user_id := (SELECT id FROM users WHERE phone = '13800138000' LIMIT 1);

SET @hs_problem := 'a2000001-0001-4000-8000-000000000001' COLLATE utf8mb4_unicode_ci;

DELETE FROM health_summary_items WHERE summary_id = @hs_problem;
DELETE FROM health_summaries WHERE id = @hs_problem;

INSERT INTO health_summaries (
    id, user_id, title, exam_date, exam_no, summary_text, created_at, updated_at, deleted_at
) VALUES (
    @hs_problem,
    @user_id,
    '健康问题总结',
    '2025-11-03',
    '312101033225',
    '根据首次体检报告（凭证号 312101033225）整理：当前以营养与代谢相关提示为主，血压与血脂处于需关注区间，肝肾功能及心电图未见明显器质性异常。建议先完成生活方式调整，并按复查计划随访。本总结仅供健康管理参考，不能替代执业医师诊断。',
    '2025-11-04 10:30:00',
    '2025-11-04 10:30:00',
    NULL
);

INSERT INTO health_summary_items (
    id, summary_id, sort_order, content, severity, created_at
) VALUES
(
    'b2000001-0001-4000-8000-000000000001',
    @hs_problem,
    0,
    '体重指数偏低（BMI 18.2），提示营养储备不足风险。建议增加优质蛋白与均衡膳食，配合适度抗阻运动，每 2～4 周复测体重。',
    'medium',
    '2025-11-04 10:30:00'
),
(
    'b2000001-0001-4000-8000-000000000002',
    @hs_problem,
    1,
    '诊室血压 138/86 mmHg（临界高值）。建议家庭自测并限盐；若持续 ≥140/90 mmHg，请门诊评估。',
    'medium',
    '2025-11-04 10:30:00'
),
(
    'b2000001-0001-4000-8000-000000000003',
    @hs_problem,
    2,
    'LDL-C 3.5 mmol/L，轻度偏高。建议低饱和脂肪饮食，3 个月后复查血脂谱。',
    'medium',
    '2025-11-04 10:30:00'
),
(
    'b2000001-0001-4000-8000-000000000004',
    @hs_problem,
    3,
    '空腹血糖 5.8 mmol/L（空腹血糖受损区间）。暂无糖尿病诊断依据，建议控制精制碳水并定期复查。',
    'low',
    '2025-11-04 10:30:00'
);

-- 首次导入后 GET /health-summaries 预期只有 1 条（健康问题总结 + items）
-- 「近期问题总结」「上次随访结果总结」此时不应存在
