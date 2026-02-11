import os

# Handle Render's Postgres URL format and TiDB's MySQL format
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # Render Postgres fix
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    # TiDB / MySQL fix: Ensure we use the pymysql driver
    elif database_url.startswith("mysql://"):
        database_url = database_url.replace("mysql://", "mysql+pymysql://", 1)


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'system_access_key_123'
    SQLALCHEMY_DATABASE_URI = database_url or 'sqlite:///system.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
