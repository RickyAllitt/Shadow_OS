
from app import create_app, db
from app.models import RewardItem

app = create_app()

def migrate_shop_items():
    with app.app_context():
        print(">> Migrating Shop Items...")
        
        # 1. Remove 'Video Game Session (1h)'
        item_to_remove = RewardItem.query.filter_by(name="Video Game Session (1h)").first()
        if item_to_remove:
            print(f"   Deleting '{item_to_remove.name}'...")
            db.session.delete(item_to_remove)
            
        # 2. Update 'Night Out with Friends' description or metadata if needed?
        # The prompt implies logic change, not necessarily DB data change, but good to know it exists.
        night_out = RewardItem.query.filter_by(name="Night Out with Friends").first()
        if night_out:
            print(f"   'Night Out with Friends' found (ID: {night_out.id}). Logic will be handled in code.")
            
        db.session.commit()
        print(">> Migration Complete.")

if __name__ == "__main__":
    migrate_shop_items()
