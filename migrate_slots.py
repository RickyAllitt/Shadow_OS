
from app import create_app, db
from app.models import RewardItem, Inventory
from sqlalchemy import or_

app = create_app()

def migrate_slots():
    with app.app_context():
        # 1. Update RewardItems (The definitions)
        print(">> Migrating Item Definitions...")
        
        # Maps: Old Slot -> New Slot
        migrations = {
            'offhand': 'accessory',
            'feet': 'accessory',
            'hands': 'accessory',
            'back': 'body' # Back items like cloaks map to body? Or accessory? Plan said 'body'. 
            # Re-reading plan: Plan mentions "Cloaks (Back) -> body or accessory? ... Let's go with accessory for now as 'extra gear'".
            # Wait, the plan text says: "Cloaks (Back) -> body or accessory? ... Let's go with accessory for now as 'extra gear'".
            # Actually, looking at the plan: "Cloaks (Back) -> body or accessory? ... Let's go with accessory for now as 'extra gear'". 
            # WAIT. The user prompt says "only be able to have 4 items". 
            # If I map Cloak to Accessory, he can have Ring + Cloak? NO. Because Slot is unique.
            # So unique 'accessory' slot means ONE accessory total.
            # So Ring OR Shield OR Boots OR Gloves OR Cloak.
            # That is a harsh limit but it fits "4 items of equipment".
        }
        
        # Applying the plan's mapping (Plan actually decided Accessory for Cloak? "Let's go with accessory for now")
        # Let's double check the approved artifact text from previous turn.
        # "Clocks (Back) -> body or accessory? ... Let's go with accessory for now"
        # Okay, mapping 'back' -> 'accessory'.
        
        migrations['back'] = 'accessory'

        items = RewardItem.query.filter(RewardItem.slot.in_(migrations.keys())).all()
        for item in items:
            new_slot = migrations[item.slot]
            print(f"   Refactoring '{item.name}': {item.slot} -> {new_slot}")
            item.slot = new_slot
            
        # 2. Unequip Conflicting Items (Inventory)
        # If a player has a Ring (Accessory) AND a Shield (Offhand->Accessory), they now have two Accessories equipped.
        # We must unequip one.
        
        print(">> Validating Player Inventories...")
        players = db.session.query(Inventory.player_id).distinct().all()
        for (pid,) in players:
            # Check for multiple accessories equipped
            # We need to refresh the session or re-query to see the updated RewardItem slots?
            # RewardItem updates are in session but not committed. Querying via relationship relies on DB state usually?
            # Let's commit item updates first.
            pass
        
        db.session.commit()
        
        # Now check for duplicates
        for (pid,) in players:
            equipped_accessories = db.session.query(Inventory).join(RewardItem).filter(
                Inventory.player_id == pid,
                Inventory.is_equipped == True,
                RewardItem.slot == 'accessory'
            ).all()
            
            if len(equipped_accessories) > 1:
                print(f"   Player {pid} has {len(equipped_accessories)} accessories equipped. Cleaning up...")
                # Keep the first one, unequip the rest
                for i in range(1, len(equipped_accessories)):
                    item_to_remove = equipped_accessories[i]
                    item_to_remove.is_equipped = False
                    print(f"      Unequipped {item_to_remove.item.name}")
                    
        db.session.commit()
        print(">> Migration Complete.")

if __name__ == "__main__":
    migrate_slots()
