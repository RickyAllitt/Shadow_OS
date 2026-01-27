import unittest
from app import create_app
from app.extensions import db
from app.models import Player, Quest
from app.services import calculate_rewards, calculate_xp_required, process_quest_completion, check_daily_reset
from datetime import datetime, timedelta, timezone
from config import Config

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

class TestEconomy(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # Create Player
        self.player = Player(name="TestPlayer", xp=0, xp_required=100, gold=0, level=1, intelligence=10, last_daily_reset=datetime.now(timezone.utc))
        db.session.add(self.player)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_xp_curve(self):
        self.assertEqual(calculate_xp_required(1), 100)
        self.assertEqual(calculate_xp_required(2), 125)
        self.assertGreater(calculate_xp_required(6), 300)

    def test_rewards(self):
        xp, gold, coins = calculate_rewards('C')
        self.assertEqual(xp, 60)
        self.assertEqual(gold, 0)
        
        xp, gold, coins = calculate_rewards('A')
        self.assertEqual(xp, 500)
        self.assertEqual(gold, 300)

    def test_quest_completion(self):
        quest = Quest(title="Test Quest", rank="C", xp_reward=60, gold_reward=50, player_id=self.player.id)
        db.session.add(quest)
        db.session.commit()
        
        # Player has 10 INT -> +5% XP
        # Rank C = 60 XP. +5% = 63 XP.
        
        xp_gain, gold_gain, coin_gain, leveled_up, daily_bonus, can_arise = process_quest_completion(self.player, quest)
        
        self.assertEqual(xp_gain, 63)
        self.assertEqual(gold_gain, 0) # Rank C gives 0 Gold now (only B+ gives gold)
        self.assertEqual(self.player.xp, 63)
        self.assertFalse(leveled_up)
        self.assertEqual(self.player.gold, 0)
        self.assertTrue(quest.is_completed)

    def test_level_up(self):
        self.player.xp = 90
        self.player.xp_required = 100
        
        quest = Quest(title="Big Quest", rank="B", xp_reward=150, gold_reward=200, player_id=self.player.id) # 150 XP
        db.session.add(quest)
        db.session.commit()
        
        # 150 XP + 5% = 157 XP. Total 90 + 157 = 247.
        # Level 1 requires 100.
        # Surplus 147. Level becomes 2. New Req = 125.
        
        _, _, _, leveled_up, _, _ = process_quest_completion(self.player, quest)
        
        self.assertTrue(leveled_up)
        self.assertEqual(self.player.level, 3)
        self.assertEqual(self.player.xp, 22)
        self.assertEqual(self.player.xp_required, 156)

    def test_penalty_stage_1_debuff(self):
        # Mock yesterday
        yesterday = datetime.now(timezone.utc) - timedelta(days=1, hours=1)
        self.player.last_daily_reset = yesterday
        
        # Create a missed daily
        daily = Quest(title="Daily Routine", is_daily=True, is_completed=False, player_id=self.player.id)
        db.session.add(daily)
        db.session.commit()
        
        check_daily_reset(self.player)
        
        self.assertEqual(self.player.consecutive_missed_days, 1)
        self.assertTrue(self.player.has_debuff)
        self.assertFalse(self.player.in_penalty_zone)

    def test_penalty_stage_2_lockdown(self):
        # Already missed one day
        self.player.consecutive_missed_days = 1
        self.player.has_debuff = True
        yesterday = datetime.now(timezone.utc) - timedelta(days=1, hours=1)
        self.player.last_daily_reset = yesterday
        
        daily = Quest(title="Daily Routine", is_daily=True, is_completed=False, player_id=self.player.id)
        db.session.add(daily)
        db.session.commit()
        
        check_daily_reset(self.player)
        
        self.assertEqual(self.player.consecutive_missed_days, 2)
        self.assertTrue(self.player.in_penalty_zone)
        
        # Check Penalty Quest Generation
        penalty = Quest.query.filter_by(is_penalty=True).first()
        self.assertIsNotNone(penalty)
        self.assertEqual(penalty.title, "PENALTY: Survival")

    def test_penalty_stage_3_level_down(self):
        self.player.level = 5
        self.player.strength = 10
        self.player.xp = 50
        self.player.consecutive_missed_days = 2
        self.player.has_debuff = True
        self.player.in_penalty_zone = True
        
        yesterday = datetime.now(timezone.utc) - timedelta(days=1, hours=1)
        self.player.last_daily_reset = yesterday
        
        # Create uncompleted daily
        daily = Quest(title="Daily Routine", is_daily=True, is_completed=False, player_id=self.player.id)
        db.session.add(daily)
        db.session.commit()
        
        check_daily_reset(self.player)
        
        self.assertEqual(self.player.consecutive_missed_days, 0) # Reset
        self.assertEqual(self.player.level, 2) # Level Down (5 - 3 = 2)
        self.assertEqual(self.player.xp, 0) # XP Reset
        self.assertEqual(self.player.strength, 7) # Stat Loss (10 - 3 = 7)
        self.assertFalse(self.player.in_penalty_zone) # Unlocked

    def test_penalty_clearance(self):
        # Setup: Player in Penalty Zone
        self.player.in_penalty_zone = True
        self.player.has_debuff = True
        self.player.consecutive_missed_days = 2
        
        # Create Penalty Quest
        penalty_quest = Quest(
            title="PENALTY: Survival", 
            rank="S", 
            player_id=self.player.id, 
            is_penalty=True, 
            xp_reward=0, 
            gold_reward=0
        )
        db.session.add(penalty_quest)
        db.session.commit()
        
        # Complete it
        process_quest_completion(self.player, penalty_quest)
        
        self.assertFalse(self.player.in_penalty_zone)
        self.assertFalse(self.player.has_debuff)
        self.assertEqual(self.player.consecutive_missed_days, 0)
        self.assertTrue(penalty_quest.is_completed)

    def test_penalty_redemption_via_dailies(self):
        """ Test that completing all dailies clears an active penalty (Day 1/2). """
        # Setup: Player has missed 1 day (Debuff Active)
        self.player.consecutive_missed_days = 1
        self.player.has_debuff = True
        
        # Create 2 Dailies
        d1 = Quest(title="D1", is_daily=True, player_id=self.player.id, rank="E")
        d2 = Quest(title="D2", is_daily=True, player_id=self.player.id, rank="E")
        db.session.add_all([d1, d2])
        db.session.commit()
        
        # Complete D1 (Partial)
        process_quest_completion(self.player, d1)
        self.assertTrue(self.player.has_debuff) # Still active
        
        # Complete D2 (Full)
        process_quest_completion(self.player, d2)
        
        # Should be cleared
        self.assertFalse(self.player.has_debuff)
        self.assertEqual(self.player.consecutive_missed_days, 0)

    def test_penalty_redemption_with_claimed_bonus(self):
        """ Test that redemption works even if the Daily Bonus was already 'claimed' (or check failed). """
        self.player.consecutive_missed_days = 1
        self.player.has_debuff = True
        
        # Simulate that bonus was already claimed today
        self.player.last_daily_bonus = datetime.now(timezone.utc)
        
        d1 = Quest(title="D1", is_daily=True, player_id=self.player.id, rank="E")
        db.session.add(d1)
        db.session.commit()
        
        process_quest_completion(self.player, d1)
        
        # Redemption should STILL happen
        self.assertFalse(self.player.has_debuff)
        self.assertEqual(self.player.consecutive_missed_days, 0)

if __name__ == '__main__':
    unittest.main()
