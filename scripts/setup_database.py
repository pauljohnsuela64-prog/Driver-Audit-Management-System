"""Interactive administrator-only provisioning, scoped exclusively to DAMS."""
import argparse
from getpass import getpass

import pymysql


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="Provision driver_audit_test_phase1 instead of production")
    args = parser.parse_args()
    database = "driver_audit_test_phase1" if args.test else "driver_audit_db"
    suffix = "test" if args.test else "prod"
    admin = input("MySQL administrator username: ").strip()
    admin_password = getpass("MySQL administrator password: ")
    app_password = getpass("New dedicated DAMS application password: ")
    migration_password = getpass("New dedicated DAMS migration password: ")
    if not app_password or not migration_password or len({admin_password, app_password, migration_password}) != 3:
        raise SystemExit("Provide nonempty application/migration passwords distinct from each other and the administrator password")
    app_user = f"dams_{suffix}_app"
    migration_user = f"dams_{suffix}_migrate"
    connection = pymysql.connect(host="localhost", user=admin, password=admin_password, charset="utf8mb4")
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (database,))
            if cursor.fetchone():
                raise SystemExit("DAMS database already exists; refusing to change existing provisioning")
            cursor.execute("SELECT User FROM mysql.user WHERE User IN (%s, %s)", (app_user, migration_user))
            if cursor.fetchone():
                raise SystemExit("DAMS accounts already exist; refusing to alter existing accounts")
            # Fixed identifiers only. MySQL DDL auto-commits: inspect partial failures.
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            cursor.execute("CREATE USER %s@'localhost' IDENTIFIED BY %s", (app_user, app_password))
            cursor.execute("CREATE USER %s@'localhost' IDENTIFIED BY %s", (migration_user, migration_password))
            cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES ON `{database}`.* TO %s@'localhost'", (migration_user,))
        print(f"Provisioned {database}; run migrations using {migration_user}.")
        print("Runtime account has no grants yet: apply database/README.md grants after migration.")
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        main()
    except pymysql.MySQLError:
        raise SystemExit("MySQL provisioning failed; administrator must inspect partial DDL before retrying") from None
