from app import create_app, db
from app.models import Player, Quest
from app.services import process_quest_completion
from datetime import datetime, timezone

app = create_app()

with app.app_context():
    # 1. Setup Test User
    player = Player.query.filter_by(name="CrashTestDummy").first()
    if player:
        db.session.delete(player)
        db.session.commit()
    
    player = Player(name="CrashTestDummy", level=1, xp=0, gold=0)
    db.session.add(player)
    db.session.commit()
    
    # 2. Create Daily Quest
    quest = Quest(
        title="Test Daily",
        rank="E",
        player_id=player.id,
        is_daily=True,
        xp_reward=10,
        stat_reward="STR"
    )
    db.session.add(quest)
    db.session.commit()
    
    print(">> processing completion...")
    try:
        # 3. Trigger Completion (This calls check_and_apply_daily_bonus)
        process_quest_completion(player, quest)
        print(">> SUCCESS: No crash.")
    except Exception as e:
        print(f">> CRASH DETECTED: {e}")
    
    # Cleanup
    db.session.delete(quest)
    db.session.delete(player)
    db.session.commit()
