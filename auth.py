import os
import json
import getpass
from pathlib import Path
from instagrapi import Client
from instagrapi.exceptions import LoginRequired, BadPassword, TwoFactorRequired, ChallengeRequired

SESSION_FILE = Path("session.json")


def _save_session(client: Client) -> None:
    SESSION_FILE.write_text(json.dumps(client.get_settings()))
    print(f"  [auth] Session saved → {SESSION_FILE}")


def _load_session(client: Client, username: str) -> bool:
    if not SESSION_FILE.exists():
        return False

    print(f"  [auth] Found existing session file — attempting reuse...")
    try:
        settings = json.loads(SESSION_FILE.read_text())
        client.set_settings(settings)
        client.get_timeline_feed()
        print("  [auth] Session is valid. ✓")
        return True
    except LoginRequired:
        print("  [auth] Saved session has expired.")
        return False
    except Exception as exc:
        print(f"  [auth] Session check failed ({exc}). Will re-login.")
        return False


def _handle_challenge(client: Client) -> None:
    print("\n  [auth] Instagram requires a security challenge.")
    print("  [auth] Check your email or phone for a verification code.\n")

    try:
        client.challenge_resolve(client.last_json)
    except Exception:
        pass

    choice = input("  Was the code sent to (e)mail or (p)hone? [e/p]: ").strip().lower()
    if choice == "p":
        client.challenge_send_phone_number()
    else:
        client.challenge_send_email()

    code = input("  [auth] Enter the 6-digit code: ").strip()
    client.challenge_send_security_code(code)

    print("  [auth] Challenge resolved. ✓")


def get_authenticated_client() -> Client:
    client = Client()
    client.delay_range = [2, 5]

    username = os.getenv("INSTAGRAM_USERNAME", "").strip()
    password = os.getenv("INSTAGRAM_PASSWORD", "").strip()

    if username and _load_session(client, username):
        return client

    if not username:
        username = input("Instagram username: ").strip()
    if not password:
        password = getpass.getpass("Instagram password: ")

    print(f"  [auth] Logging in as @{username}...")
    try:
        client.login(username, password)
    except ChallengeRequired:
        _handle_challenge(client)
    except TwoFactorRequired:
        code = input("  [auth] 2FA code: ").strip()
        client.login(username, password, verification_code=code)
    except BadPassword:
        raise SystemExit("  [auth] ✗ Incorrect password. Aborting.")

    _save_session(client)
    print(f"  [auth] Login successful. ✓")
    return client
