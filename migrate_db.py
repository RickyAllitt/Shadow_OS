import sqlite3
import os

db_path = 'instance/system.db'

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

new_columns = [
    ('is_on_vacation', 'BOOLEAN DEFAULT 0'),
    ('vacation_start_date', 'DATETIME'),
    ('vacation_end_date', 'DATETIME'),
    ('last_vacation_date', 'DATETIME'),
    ('vacation_count', 'INTEGER DEFAULT 0')
]

for col_name, col_type in new_columns:
    try:
        cursor.execute(f"ALTER TABLE player ADD COLUMN {col_name} {col_type}")
        print(f"Added column {col_name}")
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e).lower():
            print(f"Column {col_name} already exists.")
        else:
            print(f"Error adding column {col_name}: {e}")

conn.commit()
conn.close()
print("Migration completed.")
