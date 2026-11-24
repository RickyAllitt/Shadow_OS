"""Shop, inventory, consumables, equipment, titles, purchases, penalty text and point allocation routes."""
from app.extensions import db
from app.models import Player, Quest, RewardItem, Inventory, PurchaseLog, Title, PlayerTitle


def me():
    db.session.expire_all()
    return Player.query.filter_by(name="AuthUser").first()


def item(**kw):
    defaults = {'name': 'Thing', 'cost': 10, 'currency': 'coins', 'item_type': 'consumable', 'stock': -1}
    i = RewardItem(**{**defaults, **kw})
    db.session.add(i)
    db.session.commit()
    return i.id


def give(item_id, equipped=False):
    inv = Inventory(player_id=me().id, item_id=item_id, is_equipped=equipped)
    db.session.add(inv)
    db.session.commit()
    return inv.id


# --- shop & buying ---

def test_shop_page_states(auth_client, app):
    owned = item(name='Owned Gear', item_type='equipment', slot='weapon', stat_bonus='STR', stat_value=1)
    give(owned)
    item(name='Bagged Potion')
    give(Inventory.query.count() and RewardItem.query.filter_by(name='Bagged Potion').first().id)
    item(name='Too Pricey', cost=99999)
    item(name='Affordable', cost=0)
    page = auth_client.get('/shop').data
    assert b'OWNED' in page and b'IN BAG' in page
    assert b'NEED 99,999 MORE C' in page
    assert b'data-cost="0 C"' in page


def test_buy_json_coins_success_and_duplicate(auth_client, app, csrf_token):
    p = me(); p.coins = 50; db.session.commit()
    iid = item(name='Gear', cost=30, item_type='equipment', slot='weapon', stat_bonus='STR', stat_value=2)
    r = auth_client.post(f'/buy/{iid}?json=1', headers={'X-CSRFToken': csrf_token}).get_json()
    assert r['success'] and r['new_coins'] == 20 and r['item_details']['type'] == 'equipment'
    assert PurchaseLog.query.filter_by(item_name='Gear').count() == 1
    r = auth_client.post(f'/buy/{iid}?json=1', headers={'X-CSRFToken': csrf_token}).get_json()
    assert not r['success'] and 'already own' in r['message']


def test_buy_json_insufficient_funds(auth_client, app, csrf_token):
    coin_item = item(name='Coin Item', cost=1000)
    gold_item = item(name='Gold Item', cost=1000, currency='gold')
    assert auth_client.post(f'/buy/{coin_item}?json=1', headers={'X-CSRFToken': csrf_token}).get_json()['message'] == 'Not enough coins.'
    assert auth_client.post(f'/buy/{gold_item}?json=1', headers={'X-CSRFToken': csrf_token}).get_json()['message'] == 'Insufficient Funds.'
    assert Inventory.query.count() == 0


def test_buy_out_of_stock_and_missing_item(auth_client, app, csrf_token):
    iid = item(name='Gone', stock=0, cost=0)
    page = auth_client.post(f'/buy/{iid}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Out of Stock' in page
    assert auth_client.post('/buy/9999', data={'csrf_token': csrf_token}).status_code == 302


def test_buy_coins_without_json_flashes(auth_client, app, csrf_token):
    iid = item(name='Cheap', cost=1000)
    page = auth_client.post(f'/buy/{iid}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Not enough coins' in page


# --- consumables ---

def test_elixir_refused_when_already_rested(auth_client, app, csrf_token):
    p = me(); p.condition = 'WELL RESTED'; db.session.commit()
    inv = give(item(name='Elixir of Life'))
    page = auth_client.post(f'/use_item/{inv}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'already fully rested' in page
    assert db.session.get(Inventory, inv) is not None


def test_elixir_cures_tired(auth_client, app, csrf_token):
    p = me(); p.condition = 'TIRED'; p.sleep_streak = 0; db.session.commit()
    inv = give(item(name='Elixir of Life'))
    auth_client.post(f'/use_item/{inv}', data={'csrf_token': csrf_token})
    p = me()
    assert p.condition == 'WELL RESTED' and p.sleep_streak == 1 and p.last_sleep_duration >= 8
    assert db.session.get(Inventory, inv) is None


def test_night_out_completes_dailies(auth_client, app, csrf_token):
    p = me()
    db.session.add_all([Quest(title='D1', is_daily=True, player=p), Quest(title='D2', is_daily=True, player=p)])
    db.session.commit()
    inv = give(item(name='Night Out with Friends', currency='gold'))
    page = auth_client.post(f'/use_item/{inv}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Successfully completed 2 daily quests' in page
    assert all(q.is_completed for q in Quest.query.filter_by(is_daily=True))


def test_stat_consumable_and_equipment_guard(auth_client, app, csrf_token):
    before = me().strength
    inv = give(item(name='Power Potion', stat_bonus='STR', stat_value=2))
    auth_client.post(f'/use_item/{inv}', data={'csrf_token': csrf_token, 'redirect_to': 'inventory'})
    assert me().strength == before + 2

    gear = give(item(name='Sword', item_type='equipment', slot='weapon', stat_bonus='STR', stat_value=1))
    page = auth_client.post(f'/use_item/{gear}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Cannot consume equipment' in page
    page = auth_client.post('/use_item/9999', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Item not found' in page


# --- equipment ---

def test_equip_swaps_item_in_same_slot(auth_client, app, csrf_token):
    a = give(item(name='Sword A', item_type='equipment', slot='weapon', stat_bonus='STR', stat_value=1), equipped=True)
    b = give(item(name='Sword B', item_type='equipment', slot='weapon', stat_bonus='STR', stat_value=5))
    r = auth_client.post(f'/equip_item/{b}', data={'csrf_token': csrf_token, 'redirect_to': 'inventory'})
    assert r.headers['Location'].endswith('/inventory')
    db.session.expire_all()
    assert not db.session.get(Inventory, a).is_equipped and db.session.get(Inventory, b).is_equipped

    r = auth_client.post(f'/unequip_item/{b}', data={'csrf_token': csrf_token})
    assert r.headers['Location'].endswith('/')
    db.session.expire_all()
    assert not db.session.get(Inventory, b).is_equipped


def test_equip_rejects_consumables_and_unknown_items(auth_client, app, csrf_token):
    potion = give(item(name='Potion'))
    page = auth_client.post(f'/equip_item/{potion}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Cannot equip this item' in page
    page = auth_client.post('/unequip_item/9999', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Item not found' in page


def test_inventory_page_lists_items(auth_client, app):
    give(item(name='Shiny Sword', item_type='equipment', slot='weapon', stat_bonus='STR', stat_value=1), equipped=True)
    page = auth_client.get('/inventory').data
    assert b'Shiny Sword' in page and b'inv-row-equipped' in page


# --- purchases ---

def test_claim_purchase_flow(auth_client, app, csrf_token):
    log = PurchaseLog(player_id=me().id, item_name='Snack', cost=5)
    db.session.add(log); db.session.commit()
    page = auth_client.post(f'/claim_purchase/{log.id}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Consumed: Snack' in page
    page = auth_client.post(f'/claim_purchase/{log.id}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Already claimed' in page
    page = auth_client.post('/claim_purchase/9999', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Invalid item' in page


# --- titles ---

def test_equip_title_route(auth_client, app, csrf_token):
    t = Title(name='Tester', unlock_condition='manual'); db.session.add(t); db.session.commit()
    page = auth_client.post(f'/equip_title/{t.id}', data={'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Title not unlocked' in page
    db.session.add(PlayerTitle(player=me(), title=t)); db.session.commit()
    auth_client.post(f'/equip_title/{t.id}', data={'csrf_token': csrf_token})
    assert me().current_title_id == t.id


# --- penalty description ---

def test_update_penalty_description(auth_client, app, csrf_token):
    page = auth_client.post('/update_penalty', data={'penalty_description': ' ', 'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'cannot be empty' in page
    page = auth_client.post('/update_penalty', data={'penalty_description': 'Run 5k', 'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Rqd: 250 Coins' in page
    p = me(); p.coins = 300; db.session.commit()
    auth_client.post('/update_penalty', data={'penalty_description': ' Run 5k ', 'csrf_token': csrf_token})
    p = me()
    assert p.penalty_description == 'Run 5k' and p.coins == 50


# --- ability points ---

def test_allocate_points_json_and_form(auth_client, app, csrf_token):
    p = me(); p.attribute_points = 3; base = p.vitality; db.session.commit()
    r = auth_client.post('/allocate_points', json={'VIT': 2}, headers={'X-CSRFToken': csrf_token}).get_json()
    assert r == {'success': True, 'msg': 'Attributes updated.'}
    assert me().vitality == base + 2 and me().attribute_points == 1

    r = auth_client.post('/allocate_points', json={'VIT': 'lots'}, headers={'X-CSRFToken': csrf_token}).get_json()
    assert r['msg'] == 'Invalid input.'
    r = auth_client.post('/allocate_points', json={'VIT': 5}, headers={'X-CSRFToken': csrf_token}).get_json()
    assert r['msg'] == 'Not enough ability points.'

    page = auth_client.post('/allocate_points', data={'INT': '1', 'csrf_token': csrf_token}, follow_redirects=True).data
    assert b'Attributes updated' in page
