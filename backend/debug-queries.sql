-- ============================================================
-- Train Agent SQLite 调试查询
-- 使用方式: cd backend && sqlite3 data/train_agent.db < debug-queries.sql
-- 或交互式: sqlite3 data/train_agent.db 然后逐条执行
-- ============================================================

-- 美化输出
.mode column
.headers on
.width 36 36 20 20

-- ============================================================
-- 1. 总览：各表记录数
-- ============================================================
SELECT 'workspace' AS "表", COUNT(*) AS "记录数" FROM workspace
UNION ALL
SELECT 'document', COUNT(*) FROM document
UNION ALL
SELECT 'task', COUNT(*) FROM task;

-- ============================================================
-- 2. Workspace 列表
-- ============================================================
SELECT id, user_id, name, created_at FROM workspace ORDER BY created_at DESC;

-- ============================================================
-- 3. Document 列表（含状态）
-- ============================================================
SELECT
    d.id,
    d.filename,
    d.file_type,
    d.status,
    d.storage_path,
    SUBSTR(d.summary, 1, 60) AS summary_preview,
    d.created_at,
    w.name AS workspace_name
FROM document d
LEFT JOIN workspace w ON d.workspace_id = w.id
ORDER BY d.created_at DESC;

-- ============================================================
-- 4. 错误状态的文档（排查上传失败）
-- ============================================================
SELECT id, filename, file_type, status, storage_path, created_at
FROM document
WHERE status = 'error'
ORDER BY created_at DESC;

-- ============================================================
-- 5. Task/产出列表
-- ============================================================
SELECT
    t.id,
    t.type,
    t.title,
    t.status,
    t.result_data,
    t.created_at,
    t.updated_at,
    w.name AS workspace_name
FROM task t
LEFT JOIN workspace w ON t.workspace_id = w.id
ORDER BY t.created_at DESC;

-- ============================================================
-- 6. 指定 Workspace 的所有数据（替换 <WORKSPACE_ID>）
-- ============================================================
-- SELECT * FROM document WHERE workspace_id = '<WORKSPACE_ID>';
-- SELECT * FROM task WHERE workspace_id = '<WORKSPACE_ID>';

-- ============================================================
-- 7. 按 workspace 统计文档和任务数量
-- ============================================================
SELECT
    w.id,
    w.name,
    (SELECT COUNT(*) FROM document d WHERE d.workspace_id = w.id) AS doc_count,
    (SELECT COUNT(*) FROM document d WHERE d.workspace_id = w.id AND d.status = 'ready') AS doc_ready,
    (SELECT COUNT(*) FROM document d WHERE d.workspace_id = w.id AND d.status = 'error') AS doc_error,
    (SELECT COUNT(*) FROM task t WHERE t.workspace_id = w.id) AS task_count,
    (SELECT COUNT(*) FROM task t WHERE t.workspace_id = w.id AND t.status = 'completed') AS task_done
FROM workspace w
ORDER BY w.created_at DESC;

-- ============================================================
-- 8. 清理操作（谨慎使用！取消注释后执行）
-- ============================================================
-- 删除所有错误文档:
-- DELETE FROM document WHERE status = 'error';

-- 删除指定 workspace 的所有数据:
-- DELETE FROM task WHERE workspace_id = '<WORKSPACE_ID>';
-- DELETE FROM document WHERE workspace_id = '<WORKSPACE_ID>';
-- DELETE FROM workspace WHERE id = '<WORKSPACE_ID>';

-- 清空所有表:
-- DELETE FROM task;
-- DELETE FROM document;
-- DELETE FROM workspace;
