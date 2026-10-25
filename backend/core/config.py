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


def runtime_database_url():
    """Never reuse DATABASE_URL, which is reserved for migration maintenance."""
    load_dotenv()
    value = os.getenv("DAMS_PROD_RUNTIME_URL")
    if not value:
        raise ValueError("DAMS_PROD_RUNTIME_URL is required")
    try:
        url = make_url(value)
        if (url.drivername != "mysql+pymysql" or url.database != "driver_audit_db"
                or url.username != "dams_prod_app" or not url.password or not url.host
                or set(url.query) - {"charset"}
                or url.query.get("charset", "utf8mb4") != "utf8mb4"):
            raise ValueError
    except Exception:
        raise ValueError("Configure the dedicated DAMS production runtime account") from None
    return url
