import os
from dotenv import load_dotenv

# Load .env BEFORE creating app
load_dotenv()

from app import create_app, db
from app.models import Player
from sqlalchemy import text

app = create_app()

def delete_users():
    with app.app_context():
        # Verify DB Connection
        print(f"Connected to: {app.config['SQLALCHEMY_DATABASE_URI']}")
        
        # Verify we are NOT on SQLite if production is intended
        if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
            print("WARNING: Connected to SQLite! Checks .env loading.")
        
        # List ALL users first
        all_players = Player.query.all()
        print(f"Current Users in DB ({len(all_players)}):")
        for p in all_players:
            print(f"- ID: {p.id} | Name: {p.name} | Level: {p.level}")

        target_names = ["Player One", "Ricky", "Ricardo"]
        
        found_any = False
        
        for name in target_names:
            # Case insensitive search
            users = Player.query.filter(Player.name.ilike(name)).all()
            if users:
                found_any = True
                for user in users:
                    try:
                        db.session.delete(user)
                        print(f">> DELETING USER: {user.name} (ID: {user.id})")
                    except Exception as e:
                        print(f"!! Error preparing delete for {name}: {e}")
            else:
                print(f"-- User not found: {name}")
                
        if found_any:
            try:
                db.session.commit()
                print(">> COMMIT SUCCESSFUL.")
            except Exception as e:
                db.session.rollback()
                print(f"!! COMMIT FAILED: {e}")
        else:
            print("No target users found to delete.")
            
        # Verify
        print("Verifying remaining users...")
        remaining = Player.query.all()
        for p in remaining:
            print(f"- ID: {p.id} | Name: {p.name}")

if __name__ == "__main__":
    delete_users()
