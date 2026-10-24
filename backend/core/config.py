import os

from dotenv import load_dotenv
from sqlalchemy.engine import make_url


def database_url():
    load_dotenv()
    value = os.getenv("DATABASE_URL")
    if not value:
        raise ValueError("DATABASE_URL is required; configure dedicated DAMS credentials")
    url = make_url(value)
    if url.drivername != "mysql+pymysql" or url.database != "driver_audit_db":
        raise ValueError("DATABASE_URL must target mysql+pymysql and driver_audit_db")
    if not url.username or not url.password or url.username.lower() == "root":
        raise ValueError("A dedicated non-root DAMS account and password are required")
    return url
