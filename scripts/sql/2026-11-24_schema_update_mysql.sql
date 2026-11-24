-- Shadow OS schema update for MySQL / TiDB (Nov 2026 overhaul).
--
-- Run ONCE as the database admin (e.g. TiDB Cloud SQL editor) when the app's own database user
-- is not allowed to CREATE/ALTER tables. Afterwards the app finds everything in place on startup.
-- If a statement reports "Duplicate column" or "Table already exists", that part is already done:
-- skip it and continue. Replace `test` with your database name if different.

USE test;

-- 1) Room for the new secure password hashes (old: 64 chars; scrypt hashes are ~160)
ALTER TABLE player MODIFY password_hash VARCHAR(255) NULL;

-- 2) New player columns: XP debt, streak freezes, Hardcore, timezone, reminder time
ALTER TABLE player ADD COLUMN xp_debt INTEGER DEFAULT 0;
ALTER TABLE player ADD COLUMN streak_freezes INTEGER DEFAULT 0;
ALTER TABLE player ADD COLUMN hardcore BOOL DEFAULT FALSE;
ALTER TABLE player ADD COLUMN hardcore_since DATETIME NULL;
ALTER TABLE player ADD COLUMN timezone VARCHAR(50) DEFAULT 'Europe/Madrid';
ALTER TABLE player ADD COLUMN reminder_time VARCHAR(5) DEFAULT '18:00';

-- 3) Measured quests
ALTER TABLE quest ADD COLUMN metric_target FLOAT NULL;
ALTER TABLE quest ADD COLUMN metric_unit VARCHAR(20) NULL;

-- 4) New tables (order matters: kudos references activity_event)
CREATE TABLE activity_event (
    id INTEGER NOT NULL AUTO_INCREMENT,
    player_id INTEGER NOT NULL,
    occurred_at DATETIME,
    week_start DATE NOT NULL,
    kind VARCHAR(20) NOT NULL,
    points FLOAT,
    minutes INTEGER,
    success BOOL,
    `rank` VARCHAR(2),
    stat VARCHAR(3),
    units FLOAT,
    value FLOAT,
    quest_id INTEGER,
    PRIMARY KEY (id),
    FOREIGN KEY (player_id) REFERENCES player (id)
);
CREATE INDEX ix_activity_event_player_id ON activity_event (player_id);
CREATE INDEX ix_activity_event_quest_id ON activity_event (quest_id);
CREATE INDEX ix_activity_event_week_start ON activity_event (week_start);

CREATE TABLE personal_reward (
    id INTEGER NOT NULL AUTO_INCREMENT,
    player_id INTEGER NOT NULL,
    name VARCHAR(60) NOT NULL,
    cost INTEGER NOT NULL,
    created_at DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY (player_id) REFERENCES player (id)
);
CREATE INDEX ix_personal_reward_player_id ON personal_reward (player_id);

CREATE TABLE raid (
    id INTEGER NOT NULL AUTO_INCREMENT,
    title VARCHAR(80) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    target FLOAT NOT NULL,
    stat VARCHAR(3),
    created_by INTEGER,
    created_at DATETIME,
    ends_at DATETIME NOT NULL,
    status VARCHAR(12),
    completed_at DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY (created_by) REFERENCES player (id)
);

CREATE TABLE rivalry (
    id INTEGER NOT NULL AUTO_INCREMENT,
    player_id INTEGER NOT NULL,
    rival_id INTEGER NOT NULL,
    created_at DATETIME,
    PRIMARY KEY (id),
    UNIQUE (player_id),
    FOREIGN KEY (player_id) REFERENCES player (id),
    FOREIGN KEY (rival_id) REFERENCES player (id)
);

CREATE TABLE kudos (
    id INTEGER NOT NULL AUTO_INCREMENT,
    event_id INTEGER NOT NULL,
    from_player_id INTEGER NOT NULL,
    emoji VARCHAR(8) NOT NULL,
    created_at DATETIME,
    PRIMARY KEY (id),
    CONSTRAINT uq_kudos_once UNIQUE (event_id, from_player_id),
    FOREIGN KEY (event_id) REFERENCES activity_event (id),
    FOREIGN KEY (from_player_id) REFERENCES player (id)
);
CREATE INDEX ix_kudos_event_id ON kudos (event_id);

CREATE TABLE raid_contribution (
    id INTEGER NOT NULL AUTO_INCREMENT,
    raid_id INTEGER NOT NULL,
    player_id INTEGER NOT NULL,
    amount FLOAT NOT NULL,
    created_at DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY (raid_id) REFERENCES raid (id),
    FOREIGN KEY (player_id) REFERENCES player (id)
);
CREATE INDEX ix_raid_contribution_raid_id ON raid_contribution (raid_id);

-- Check: SHOW TABLES;  SHOW COLUMNS FROM player LIKE 'xp_debt';  SHOW COLUMNS FROM quest LIKE 'metric%';
