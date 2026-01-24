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
    app.run(debug=debug_mode)
