import os
from dotenv import load_dotenv
load_dotenv()

from app import create_app, db
from sqlalchemy import text

app = create_app()

def add_column():
    with app.app_context():
        print(f"Connected to: {app.config['SQLALCHEMY_DATABASE_URI']}")
        try:
            # Check if column exists first
            with db.engine.connect() as conn:
                result = conn.execute(text("SHOW COLUMNS FROM player LIKE 'attribute_points'"))
                if result.fetchone():
                    print("Column 'attribute_points' already exists.")
                else:
                    print("Adding 'attribute_points' column...")
                    conn.execute(text("ALTER TABLE player ADD COLUMN attribute_points INTEGER DEFAULT 0"))
                    print("Column added successfully.")
                    commit = True
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    add_column()
