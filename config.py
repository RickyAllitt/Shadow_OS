import os

# Handle Render's Postgres URL format and TiDB's MySQL format
database_url = os.environ.get('DATABASE_URL')

if database_url:
    # Render Postgres fix
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    
    # TiDB / MySQL fix: Ensure we use the pymysql driver
    # Handle "mysql://" (default) and "mysql+mysqldb://" (often provided by dashboards)
    elif "mysql://" in database_url:
        database_url = database_url.replace("mysql://", "mysql+pymysql://", 1)
    elif "mysql+mysqldb://" in database_url:
        database_url = database_url.replace("mysql+mysqldb://", "mysql+pymysql://", 1)

    # Clean up unsupported SSL arguments for pymysql
    if "ssl_mode=" in database_url:
        import re
        database_url = re.sub(r'ssl_mode=[^&]+&?', '', database_url)
        if database_url.endswith('?'): database_url = database_url[:-1]


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'system_access_key_123'
    SQLALCHEMY_DATABASE_URI = database_url or 'sqlite:///system.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
