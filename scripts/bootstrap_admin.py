"""Interactive initial administrator setup; --recover explicitly resets an app admin."""
import argparse
from getpass import getpass, GetPassWarning
import warnings

from backend.core.config import runtime_database_url
from backend.core.database import make_engine
from backend.schemas.auth import BootstrapRequest
from backend.services.bootstrap import bootstrap_admin


def prompt_password(prompt):
    # getpass warns before falling back to echoed stdin; refuse that fallback.
    with warnings.catch_warnings():
        warnings.simplefilter("error", GetPassWarning)
        return getpass(prompt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recover", action="store_true", help="Reset an existing application ADMIN and revoke all sessions")
    args = parser.parse_args()
    username = input("Application administrator username: ").strip()
    full_name = "Recovery" if args.recover else input("Administrator full name: ").strip()
    password = prompt_password("New password (15-128 characters): ")
    if password != prompt_password("Confirm new password: "):
        raise ValueError("Passwords do not match")
    if args.recover and input("Type RECOVER to reset this application admin and revoke sessions: ") != "RECOVER":
        raise ValueError("Recovery not confirmed")
    request = BootstrapRequest(username=username, full_name=full_name, password=password)
    engine = make_engine(runtime_database_url())
    try:
        bootstrap_admin(engine, request, recover=args.recover)
    finally:
        engine.dispose()
    print("Application administrator recovery complete." if args.recover else "Initial application administrator created.")


if __name__ == "__main__":
    try:
        main()
    except (Exception, KeyboardInterrupt):
        raise SystemExit("Administrator setup failed or was refused. No credentials are displayed; check configuration and existing accounts.") from None
