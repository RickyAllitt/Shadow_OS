import sqlite3
import os

db_path = 'instance/system.db'

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()


updates = {
    'player': [
        ('is_on_vacation', 'BOOLEAN DEFAULT 0'),
        ('vacation_start_date', 'DATETIME'),
        ('vacation_end_date', 'DATETIME'),
        ('last_vacation_date', 'DATETIME'),
        ('vacation_count', 'INTEGER DEFAULT 0'),
        ('settings_audio', 'BOOLEAN DEFAULT 1'),
        ('settings_music', 'BOOLEAN DEFAULT 1')
    ],
    'daily_snapshot': [
        ('quests_completed', 'INTEGER DEFAULT 0')
    ]
}

for table, columns in updates.items():
    for col_name, col_type in columns:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
            print(f"Added column {col_name} to {table}")
        except sqlite3.OperationalError as e:
            if 'duplicate column name' in str(e).lower() or 'no such table' in str(e).lower():
                print(f"Skipping {col_name} in {table}: {e}")
            else:
                print(f"Error adding column {col_name} to {table}: {e}")

conn.commit()
conn.close()
print("Migration completed.")
