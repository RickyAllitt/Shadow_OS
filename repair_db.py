
from app import create_app, db
from app.services import seed_database
from sqlalchemy import inspect

app = create_app()

def repair_db():
    with app.app_context():
        print(">> Inspecting Database...")
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"   Existing Tables: {tables}")
        
        if 'player' not in tables:
            print(">> CRITICAL: 'player' table missing. Recreating Schema...")
            db.create_all()
            print(">> Schema Created.")
        else:
            print(">> 'player' table exists. Checking schema integrity...")
            # We could try to migrate/upgrade here if needed, but db.create_all helps for missing parts.
            db.create_all() 
            
        print(">> Seeding Database...")
        seed_database()
        print(">> Repair Complete.")

if __name__ == "__main__":
    repair_db()
