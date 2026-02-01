import os

# Handle Render's Postgres URL format
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'system_access_key_123'
    SQLALCHEMY_DATABASE_URI = database_url or 'sqlite:///system.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
