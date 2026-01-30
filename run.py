from app import create_app
from app.extensions import db
from app.services import seed_database
import os
from dotenv import load_dotenv

load_dotenv()

app = create_app()

# Initialize DB and Seeder
with app.app_context():
    db.create_all()
    seed_database()

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', 'True').lower() in ['true', '1', 't']
    
    # SCHEDULER CONFIGURATION
    # Only run scheduler in the main process (reloader spawns a child, we don't want doubles)
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not debug_mode:
        from app.extensions import scheduler
        from app.services import check_daily_completion_status, check_upcoming_deadlines
        
        # Job 1: Daily Check at 18:00 (6 PM)
        # Note: We pass 'app' instance explicitly via args if needed, but context is handled inside function wrapper usually.
        # However, APScheduler in Flask context needs app context.
        # My service functions take 'app_instance' as arg.
        
        scheduler.add_job(
            id='daily_check_1800',
            func=check_daily_completion_status,
            args=[app],
            trigger='cron',
            hour=18,
            minute=0
        )
        
        # Job 2: Deadline Check at 08:00 (8 AM)
        scheduler.add_job(
            id='deadline_check_0800',
            func=check_upcoming_deadlines,
            args=[app],
            trigger='cron',
            hour=8,
            minute=0
        )
        
        print(">> SYSTEM: Scheduler Jobs Registered (18:00 Check, 08:00 Reminders)")

    app.run(debug=debug_mode)
