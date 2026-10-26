"""Provision only a fresh Docker MySQL instance on a GitHub-hosted runner."""
import os
from pathlib import Path
import secrets
import subprocess
import time

from alembic import command
from alembic.config import Config
import pymysql
from sqlalchemy import inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from backend.core.database import make_engine

CONTAINER = "dams-ci-mysql"
DATABASE = "driver_audit_test_phase1"


def require_hosted_runner():
    if os.getenv("GITHUB_ACTIONS") != "true" or os.getenv("RUNNER_ENVIRONMENT") != "github-hosted":
        raise SystemExit("Provisioning requires a disposable GitHub-hosted runner")


def main():
    require_hosted_runner()
    output = Path(os.environ["GITHUB_ENV"])
    root_password, migrate_password, app_password = [secrets.token_urlsafe(32) for _ in range(3)]
    for password in [root_password, migrate_password, app_password]:
        print(f"::add-mask::{password}", flush=True)
    environment = os.environ | {"MYSQL_ROOT_PASSWORD": root_password}
    # Bind an ephemeral port only on runner loopback. Pass root credentials by
    # environment name, never as a command argument or docker logs output.
    subprocess.run(["docker", "run", "--detach", "--name", CONTAINER,
                    "--env", "MYSQL_ROOT_PASSWORD", "--env", "MYSQL_ROOT_HOST=%",
                    "--publish", "127.0.0.1::3306", "mysql:8.0"],
                   env=environment, check=True, capture_output=True)
    binding = subprocess.check_output(["docker", "port", CONTAINER, "3306/tcp"], text=True).strip()
    host, port_text = binding.split(":")
    if host != "127.0.0.1":
        raise SystemExit("MySQL must be bound exclusively to runner loopback")
    port = int(port_text)
    deadline = time.monotonic() + 120
    while True:
        try:
            admin = pymysql.connect(host=host, port=port, user="root", password=root_password,
                                    charset="utf8mb4", connect_timeout=2, autocommit=True)
            break
        except pymysql.MySQLError:
            if time.monotonic() >= deadline:
                raise SystemExit("Disposable MySQL failed readiness checks") from None
            time.sleep(2)
    try:
        with admin.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            for account, password in [("dams_test_migrate", migrate_password), ("dams_test_app", app_password)]:
                cursor.execute("CREATE USER %s@'%%' IDENTIFIED BY %s", (account, password))
            cursor.execute("SELECT @@GLOBAL.partial_revokes")
            grant_database = DATABASE if cursor.fetchone()[0] else DATABASE.replace("_", r"\_")
            cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES "
                           f"ON `{grant_database}`.* TO 'dams_test_migrate'@'%'")
        urls = {}
        for key, account, password in [("DAMS_TEST_DATABASE_URL", "dams_test_migrate", migrate_password),
                                       ("DAMS_TEST_RUNTIME_URL", "dams_test_app", app_password)]:
            urls[key] = URL.create("mysql+pymysql", username=account, password=password, host=host,
                                   port=port, database=DATABASE, query={"charset": "utf8mb4"})
        engine = make_engine(urls["DAMS_TEST_DATABASE_URL"])
        try:
            cfg = Config("alembic.ini")
            with engine.connect() as connection:
                cfg.attributes["connection"] = connection
                command.upgrade(cfg, "head")
                with admin.cursor() as cursor:
                    for table in ["users", "audit_records", "auth_sessions", "audit_events"]:
                        rights = "SELECT, INSERT" if table == "audit_events" else "SELECT, INSERT, UPDATE"
                        cursor.execute(f"GRANT {rights} ON `{DATABASE}`.`{table}` TO 'dams_test_app'@'%'")
                command.downgrade(cfg, "base")
                connection.execute(text("DROP TABLE alembic_version"))
                connection.commit()
                assert inspect(connection).get_table_names() == [], "Test schema must start empty"
        finally:
            engine.dispose()
        with output.open("a", encoding="utf-8") as handle:
            for key, url in urls.items():
                value = url.render_as_string(hide_password=False)
                print(f"::add-mask::{value}", flush=True)
                handle.write(f"{key}={value}\n")
        print("Disposable MySQL ready; restricted test accounts provisioned; schema empty.")
    finally:
        admin.close()


if __name__ == "__main__":
    try:
        main()
    except (pymysql.MySQLError, SQLAlchemyError, subprocess.SubprocessError):
        raise SystemExit("CI MySQL provisioning failed; no credential details logged") from None
