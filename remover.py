import time
import random
import logging
from typing import Optional

from instagrapi import Client
from instagrapi.exceptions import ClientError, ClientConnectionError, UserNotFound

from tqdm import tqdm

logger = logging.getLogger(__name__)

DELAY_MIN: float = 6.0
DELAY_MAX: float = 12.0
MAX_RETRIES: int = 3
BACKOFF_BASE: float = 20.0


class KillSwitchTriggered(RuntimeError):
    pass


def _random_delay() -> None:
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def _get_user_id(client: Client, username: str) -> Optional[int]:
    try:
        return client.user_id_from_username(username)
    except UserNotFound:
        logger.warning(f"@{username}: user not found — already removed or deleted.")
        return None
    except Exception as exc:
        logger.error(f"@{username}: failed to resolve user ID ({exc}).")
        return None


def _remove_follower(client: Client, username: str) -> bool:
    user_id = _get_user_id(client, username)
    if user_id is None:
        return False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            client.user_remove_follower(user_id)
            return True

        except ClientError as exc:
            msg = str(exc)
            if "429" in msg or "too many requests" in msg.lower():
                raise KillSwitchTriggered(
                    "HTTP 429 received during removal — aborting to protect account."
                )
            backoff = BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning(
                f"@{username}: API error ({exc}). "
                f"Retrying in {backoff:.0f}s... ({attempt}/{MAX_RETRIES})"
            )
            time.sleep(backoff)

        except ClientConnectionError as exc:
            backoff = BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning(
                f"@{username}: Connection error ({exc}). "
                f"Retrying in {backoff:.0f}s... ({attempt}/{MAX_RETRIES})"
            )
            time.sleep(backoff)

    logger.error(f"@{username}: exhausted retries — skipping.")
    return False


def remove_bots(client: Client, bot_usernames: list[str]) -> dict:
    removed = []
    failed = []

    print(f"\n[remover] Removing {len(bot_usernames)} bot accounts...\n")

    try:
        for username in tqdm(bot_usernames, desc="Removing bots", unit="user"):
            success = _remove_follower(client, username)

            if success:
                removed.append(username)
                tqdm.write(f"  ✓  Removed @{username}")
            else:
                failed.append(username)
                tqdm.write(f"  ✗  Failed  @{username}")

            _random_delay()

    except KillSwitchTriggered as exc:
        print(f"\n  ⛔  KILL SWITCH TRIGGERED: {exc}")
        print(
            f"  Partial results: "
            f"{len(removed)} removed, {len(failed)} failed, "
            f"{len(bot_usernames) - len(removed) - len(failed)} not attempted."
        )

    return {"removed": removed, "failed": failed}
