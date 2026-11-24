-- Shadow OS: class skills (Vanish / Insight / Fortify). TiDB / MariaDB syntax.
-- Only needed if the app's database user can't ALTER tables; otherwise the app adds these on startup.
ALTER TABLE test.player
    ADD COLUMN IF NOT EXISTS skill_ready_at DATETIME NULL,
    ADD COLUMN IF NOT EXISTS skill_armed BOOL DEFAULT FALSE;
