from app import create_app, db
from app.models import RewardItem
import os

# We need to explicitly point to the right DB instead of in-memory or default
app = create_app()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////home/ricardo/Documents/GitHub/My_App/instance/app.db'

with app.app_context():
    item = RewardItem.query.filter_by(name='Elixir of Vitality').first()
    if item:
        item.name = 'Elixir of Life'
        item.stat_bonus = None
        item.stat_value = 0
        item.stock = -1
        db.session.commit()
        print('Migrated Elixir of Vitality to Elixir of Life')
    else:
        print('Item not found or already migrated')
