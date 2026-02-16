
import os
from dotenv import load_dotenv

# Load .env BEFORE creating app
load_dotenv()

from app import create_app, db
from app.models import Player, Quest
from sqlalchemy import text

app = create_app()

def delete_quest():
    with app.app_context():
        # Verify DB Connection
        print(f"Connected to: {app.config['SQLALCHEMY_DATABASE_URI']}")
        
        target_user_name = "Ricardo"
        target_quest_title = "Climb Mount Everest"
        
        # 1. Find User
        user = Player.query.filter(Player.name == target_user_name).first()
        if not user:
            print(f"Error: User '{target_user_name}' not found.")
            return

        print(f"Found User: {user.name} (ID: {user.id})")
        
        # 2. Find ALL Matching Quests
        quests = Quest.query.filter(
            Quest.player_id == user.id,
            Quest.title.ilike(target_quest_title)
        ).all()
        
        if not quests:
            print(f"Error: No quests with title '{target_quest_title}' found for user '{user.name}'.")
            return
            
        print(f"Found {len(quests)} quests with title '{target_quest_title}'.")
        
        # 3. Delete All
        try:
            for q in quests:
                db.session.delete(q)
                print(f">> Deleting quest ID: {q.id}")
            db.session.commit()
            print(f"SUCCESS: Deleted {len(quests)} quests.")
        except Exception as e:
            db.session.rollback()
            print(f"FAILURE: Could not delete quests. Error: {e}")

if __name__ == "__main__":
    delete_quest()
