"""
Loot: equipment that drops from Gates and from big quests (unlocked with Gates at Lv 15).

Drops are real RewardItem rows (currency 'loot', never sold in the shop) added to the inventory,
so they equip through the normal slots. A duplicate is salvaged into Coins.

Rarity unlocks with level: Common/Rare from Lv 15, Epic from Lv 30, Legendary set pieces from Lv 60.
Legendary sets give a bonus for 2 and 4 equipped pieces (see SETS).
"""
import random

from app.extensions import db
from app.models import Inventory, RewardItem

SLOTS = ('weapon', 'head', 'body', 'accessory')
STATS = ('STR', 'AGI', 'INT', 'VIT', 'SNS')

RARITY_ORDER = ('common', 'rare', 'epic', 'legendary')
RARITY_LEVEL = {'common': 15, 'rare': 15, 'epic': 30, 'legendary': 60}
RARITY_STAT = {'common': (1, 2), 'rare': (3, 4), 'epic': (6, 8), 'legendary': (10, 12)}
SALVAGE_COINS = {'common': 25, 'rare': 75, 'epic': 200, 'legendary': 500}

# Chance that a completed non-daily quest drops something (from Lv 15)
QUEST_DROP_CHANCE = {'B': 0.05, 'A': 0.12, 'S': 0.30}

BASES = {
    'weapon': ('Dagger', 'Blade', 'Staff', 'Greatsword', 'Spear'),
    'head': ('Hood', 'Helm', 'Circlet', 'Mask'),
    'body': ('Coat', 'Mail', 'Robe', 'Cuirass'),
    'accessory': ('Ring', 'Amulet', 'Charm', 'Bracer'),
}
STAT_WORD = {'STR': 'Ironbound', 'AGI': 'Swift', 'INT': 'Runed', 'VIT': 'Stalwart', 'SNS': 'Keen'}
RARITY_WORD = {'common': '', 'rare': 'Gleaming', 'epic': 'Dread', 'legendary': ''}

# Legendary sets: four pieces each. 2 pieces: +5 to both set stats. 4 pieces: also +5% XP.
SETS = {
    'Abyssal Sovereign': {'stats': ('STR', 'AGI'),
                          'pieces': {'weapon': 'Abyssal Fang', 'head': 'Abyssal Crown',
                                     'body': 'Abyssal Mantle', 'accessory': 'Abyssal Seal'}},
    'Starfall Archon': {'stats': ('INT', 'SNS'),
                        'pieces': {'weapon': 'Starfall Scepter', 'head': 'Starfall Diadem',
                                   'body': 'Starfall Vestments', 'accessory': 'Starfall Orb'}},
    'Unbroken Bastion': {'stats': ('VIT', 'STR'),
                         'pieces': {'weapon': 'Bastion Hammer', 'head': 'Bastion Greathelm',
                                    'body': 'Bastion Plate', 'accessory': 'Bastion Sigil'}},
}
SET_BONUS_STAT = 5
SET_BONUS_XP = 0.05

STAT_FIELDS = {'STR': 'strength', 'AGI': 'agility', 'INT': 'intelligence', 'VIT': 'vitality', 'SNS': 'sense'}


def unlock_level(player):
    from app.progression import effective_level
    return effective_level(player)


def roll_rarity(player, rng=random, floor='common'):
    """Weighted rarity roll, limited to what the player's level has unlocked, never below `floor`."""
    level = unlock_level(player)
    weights = {'common': 60, 'rare': 30, 'epic': 8, 'legendary': 2}
    allowed = [r for r in RARITY_ORDER
               if RARITY_LEVEL[r] <= level and RARITY_ORDER.index(r) >= RARITY_ORDER.index(floor)]
    if not allowed:  # floor above what's unlocked: give the best unlocked rarity
        allowed = [max((r for r in RARITY_ORDER if RARITY_LEVEL[r] <= level), key=RARITY_ORDER.index,
                       default='common')]
    return rng.choices(allowed, weights=[weights[r] for r in allowed])[0]


def _item_spec(rarity, rng):
    slot = rng.choice(SLOTS)
    if rarity == 'legendary':
        set_name = rng.choice(sorted(SETS))
        spec = SETS[set_name]
        stat = spec['stats'][SLOTS.index(slot) % 2]
        return {'name': spec['pieces'][slot], 'slot': slot, 'stat': stat,
                'value': rng.randint(*RARITY_STAT[rarity]), 'set_name': set_name}
    stat = rng.choice(STATS)
    base = rng.choice(BASES[slot])
    name = ' '.join(w for w in (RARITY_WORD[rarity], STAT_WORD[stat], base) if w)
    lo, hi = RARITY_STAT[rarity]
    return {'name': name, 'slot': slot, 'stat': stat, 'value': hi if rarity == 'common' else rng.randint(lo, hi),
            'set_name': None}


def _item_row(spec, rarity):
    row = RewardItem.query.filter_by(name=spec['name'], currency='loot').first()
    if row is None:
        row = RewardItem(name=spec['name'], cost=0, currency='loot', stock=0, item_type='equipment',
                         stat_bonus=spec['stat'], stat_value=spec['value'], slot=spec['slot'],
                         rarity=rarity, set_name=spec['set_name'])
        db.session.add(row)
        db.session.flush()
    return row


def grant_loot(player, rng=random, floor='common', rarity=None):
    """
    Drop one item. Returns a message. Duplicates (same item already owned) are salvaged for Coins.
    """
    rarity = rarity or roll_rarity(player, rng, floor)
    row = _item_row(_item_spec(rarity, rng), rarity)
    owned = Inventory.query.filter_by(player_id=player.id, item_id=row.id).first()
    label = f"[{rarity.upper()}] {row.name} (+{row.stat_value} {row.stat_bonus})"
    if owned:
        coins = SALVAGE_COINS[rarity]
        player.coins += coins
        return f"LOOT: {label}. Already owned, salvaged for {coins} Coins."
    db.session.add(Inventory(player_id=player.id, item_id=row.id))
    extra = f" Part of the {row.set_name} set." if row.set_name else ""
    return f"LOOT DROPPED: {label}.{extra} Check your inventory."


def maybe_drop_from_quest(player, quest, rng=random):
    """Chance-based drop for non-daily B/A/S quests once Gates are unlocked. Returns a message or None."""
    if quest.is_daily or quest.is_penalty or unlock_level(player) < 15:
        return None
    chance = QUEST_DROP_CHANCE.get(quest.rank, 0)
    if chance and rng.random() < chance:
        return grant_loot(player, rng)
    return None


# ---------------------------------------------------------------- sets

def equipped_sets(player):
    """{set name: equipped piece count} for sets with at least one equipped piece."""
    counts = {}
    for inv in player.inventory:
        if inv.is_equipped and inv.item.set_name:
            counts[inv.item.set_name] = counts.get(inv.item.set_name, 0) + 1
    return counts


def set_stat_bonuses(player):
    """{'strength': 5, ...} from 2-piece set bonuses."""
    bonus = {}
    for name, count in equipped_sets(player).items():
        if count >= 2 and name in SETS:
            for stat in SETS[name]['stats']:
                field = STAT_FIELDS[stat]
                bonus[field] = bonus.get(field, 0) + SET_BONUS_STAT
    return bonus


def set_xp_bonus(player):
    return sum(SET_BONUS_XP for name, count in equipped_sets(player).items() if count >= 4 and name in SETS)


def set_summaries(player):
    """For the inventory page: each set with pieces owned/equipped and active bonuses."""
    owned = {inv.item.name: inv.is_equipped for inv in player.inventory if inv.item.set_name}
    out = []
    for name, spec in SETS.items():
        pieces = [{'slot': slot, 'name': piece, 'owned': piece in owned, 'equipped': owned.get(piece, False)}
                  for slot, piece in spec['pieces'].items()]
        if any(p['owned'] for p in pieces):
            equipped = sum(p['equipped'] for p in pieces)
            out.append({'name': name, 'stats': spec['stats'], 'pieces': pieces, 'equipped': equipped,
                        'two': equipped >= 2, 'four': equipped >= 4})
    return out
