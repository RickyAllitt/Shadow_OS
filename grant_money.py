
from app import create_app, db
from app.models import Player

app = create_app()

with app.app_context():
    # Try to find 'Ricky' (case insensitive)
    result = db.session.execute(db.select(Player).where(Player.name.ilike('%ricky%'))).scalars().first()
    
    if not result:
        print("User 'Ricky' not found. searching for 'Player One'...")
        result = db.session.execute(db.select(Player).where(Player.name == 'Player One')).scalars().first()

    if not result:
        print("No players found. Granting to ANY first player.")
        result = db.session.query(Player).first()
        
    if result:
        print(f"Granting currency to: {result.name} (Current: {result.gold} G, {result.coins} C)")
        result.gold = 50000
        result.coins = 50000
        db.session.commit()
        print(f"SUCCESS: {result.name} now has {result.gold} G and {result.coins} C.")
    else:
        print("ERROR: No players found in database.")
