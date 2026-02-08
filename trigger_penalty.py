
from app import create_app
from app.extensions import db
from app.models import Player, Quest
from datetime import datetime, timedelta, timezone

app = create_app()

with app.app_context():
    player = Player.query.filter_by(name="Ricky").first()
    if not player:
        print("Player 'Ricky' not found. searching for any player...")
        player = Player.query.first()
    
    if player:
        print(f"Applying Penalty Mode to {player.name}...")
        
        # 1. Update Player State
        player.in_penalty_zone = True
        player.consecutive_missed_days = 2
        player.has_debuff = True
        
        # 2. visual flair
        player.penalty_description = "Survival run (5km)"
        
        # 3. Create Penalty Quest if not exists
        existing = Quest.query.filter_by(player_id=player.id, is_penalty=True, is_completed=False).first()
        if existing:
            db.session.delete(existing)
            db.session.commit()
            print(">> Deleted existing penalty to apply new settings.")
            
        import pytz
        GAME_TIMEZONE = pytz.timezone('Europe/Madrid')
        now_utc = datetime.now(timezone.utc)
        now_game = now_utc.astimezone(GAME_TIMEZONE)
        today_midnight_game = now_game.replace(hour=0, minute=0, second=0, microsecond=0)
        # Next midnight in Madrid
        deadline_game = today_midnight_game + timedelta(days=1)
        deadline_utc = deadline_game.astimezone(timezone.utc)

        penalty = Quest(
            title="PENALTY: Survival run (5km)",
            rank="A",
            player_id=player.id,
            xp_reward=0,
            gold_reward=0,
            stat_reward="VIT",
            is_penalty=True,
            due_date=deadline_utc
        )
        db.session.add(penalty)
        print(">> Penalty Quest Created.")
            
        db.session.commit()
        print(">> DONE. Refresh your dashboard.")
    else:
        print(">> NO PLAYERS FOUND IN DATABASE.")
