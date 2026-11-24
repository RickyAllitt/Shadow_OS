-- Shadow OS: Gates, loot, Shadow Army grades, Second Awakening, Ascension. TiDB / MariaDB syntax.
-- Only needed if the app's database user can't CREATE/ALTER; otherwise the app does this on startup.
ALTER TABLE test.player
    ADD COLUMN IF NOT EXISTS specialization VARCHAR(20) NULL,
    ADD COLUMN IF NOT EXISTS ascensions INTEGER DEFAULT 0;
ALTER TABLE test.reward_item
    ADD COLUMN IF NOT EXISTS rarity VARCHAR(12) NULL,
    ADD COLUMN IF NOT EXISTS set_name VARCHAR(40) NULL;
ALTER TABLE test.shadow
    ADD COLUMN IF NOT EXISTS assigned_quest_id INTEGER NULL,
    ADD COLUMN IF NOT EXISTS kills INTEGER DEFAULT 0;
CREATE TABLE IF NOT EXISTS test.gate (id INTEGER NOT NULL AUTO_INCREMENT, player_id INTEGER NOT NULL, kind VARCHAR(12) NOT NULL, grade VARCHAR(2) NOT NULL, title VARCHAR(80) NOT NULL, objectives TEXT NOT NULL, target_rank VARCHAR(2), week_start DATE NOT NULL, appeared_at DATETIME, enter_by DATETIME, entered_at DATETIME, expires_at DATETIME, status VARCHAR(12) NOT NULL, finished_at DATETIME, PRIMARY KEY (id), INDEX ix_gate_player_id (player_id), FOREIGN KEY (player_id) REFERENCES test.player (id));
