import time
import random
import logging
import json
import threading
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from instagrapi import Client
from instagrapi.exceptions import (
    UserNotFound,
    PrivateAccount,
    ClientError,
    ClientConnectionError,
)
from tqdm import tqdm

logger = logging.getLogger(__name__)

DELAY_MIN: float = 2.0
DELAY_MAX: float = 5.0
MAX_RETRIES: int = 3
BACKOFF_BASE: float = 15.0
MAX_WORKERS: int = 4

BOT_MAX_FOLLOWERS: int = 50
BOT_MIN_FOLLOWING: int = 1000

REAL_OUT = Path("real.json")
FAKE_OUT = Path("fake.json")
PROGRESS_FILE = Path("progress.json")

_write_lock = threading.Lock()


class KillSwitchTriggered(RuntimeError):
    pass


def _load_progress() -> tuple[list[dict], list[dict], set[str]]:
    real = json.loads(REAL_OUT.read_text()) if REAL_OUT.exists() else []
    bots = json.loads(FAKE_OUT.read_text()) if FAKE_OUT.exists() else []
    scanned = set(json.loads(PROGRESS_FILE.read_text())) if PROGRESS_FILE.exists() else set()
    return real, bots, scanned


def _save_result(info: dict, is_bot: bool, real: list, bots: list, scanned: set) -> None:
    with _write_lock:
        scanned.add(info["username"])
        if is_bot:
            bots.append(info)
        else:
            real.append(info)
        REAL_OUT.write_text(json.dumps(real, indent=2, ensure_ascii=False))
        FAKE_OUT.write_text(json.dumps(bots, indent=2, ensure_ascii=False))
        PROGRESS_FILE.write_text(json.dumps(list(scanned), ensure_ascii=False))


def _random_delay() -> None:
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def _fetch_user_info(client: Client, username: str) -> Optional[dict]:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            user = client.user_info_by_username(username)
            return {
                "username": user.username,
                "follower_count": user.follower_count,
                "following_count": user.following_count,
                "is_private": user.is_private,
                "full_name": user.full_name,
            }

        except UserNotFound:
            logger.debug(f"@{username}: not found — skipping.")
            return None

        except PrivateAccount:
            try:
                user_id = client.user_id_from_username(username)
                user = client.user_info(user_id)
                return {
                    "username": user.username,
                    "follower_count": user.follower_count,
                    "following_count": user.following_count,
                    "is_private": True,
                    "full_name": user.full_name,
                }
            except Exception:
                logger.debug(f"@{username}: private and unreadable — skipping.")
                return None

        except ClientError as exc:
            msg = str(exc)
            if "429" in msg or "too many requests" in msg.lower():
                raise KillSwitchTriggered(
                    "HTTP 429 — Instagram is rate-limiting. "
                    "Wait at least 30 minutes before retrying."
                )
            backoff = BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning(f"@{username}: error attempt {attempt}/{MAX_RETRIES}, retrying in {backoff:.0f}s")
            time.sleep(backoff)

        except ClientConnectionError as exc:
            backoff = BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning(f"@{username}: connection error, retrying in {backoff:.0f}s ({attempt}/{MAX_RETRIES})")
            time.sleep(backoff)

    logger.error(f"@{username}: exhausted retries — skipping.")
    return None


def _is_bot(info: dict) -> bool:
    return (
        info["follower_count"] < BOT_MAX_FOLLOWERS
        and info["following_count"] > BOT_MIN_FOLLOWING
    )


def _scan_one(
    client: Client,
    username: str,
    real: list,
    bots: list,
    scanned: set,
    pbar: tqdm
) -> Optional[str]:
    try:
        info = _fetch_user_info(client, username)
        if info is not None:
            bot = _is_bot(info)
            _save_result(info, bot, real, bots, scanned)
            if bot:
                tqdm.write(
                    f"  🤖 BOT  @{username:<30} "
                    f"followers={info['follower_count']:>4}  "
                    f"following={info['following_count']:>5}"
                )
        else:
            with _write_lock:
                scanned.add(username)
                PROGRESS_FILE.write_text(json.dumps(list(scanned), ensure_ascii=False))

        _random_delay()

    except KillSwitchTriggered as exc:
        tqdm.write(f"\n  ⛔  KILL SWITCH: {exc}")
        return "kill"

    finally:
        pbar.update(1)

    return None


def scan_non_mutuals(
    client: Client,
    non_mutuals: set[str]
) -> tuple[list[dict], list[dict]]:
    real, bots, scanned = _load_progress()
    remaining = [u for u in non_mutuals if u not in scanned]

    if scanned:
        print(f"\n  [detector] Resuming — {len(scanned)} already scanned, "
              f"{len(remaining)} remaining.")
    else:
        print(f"\n  [detector] Starting fresh scan of {len(non_mutuals)} accounts.")

    print(
        f"  Bot criteria → followers < {BOT_MAX_FOLLOWERS}  AND  "
        f"following > {BOT_MIN_FOLLOWING}\n"
        f"  Workers: {MAX_WORKERS}  |  Delay per worker: {DELAY_MIN}–{DELAY_MAX}s\n"
    )

    kill_triggered = False

    with tqdm(total=len(remaining), desc="Scanning", unit="user") as pbar:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(_scan_one, client, u, real, bots, scanned, pbar): u
                for u in remaining
            }
            for future in as_completed(futures):
                result = future.result()
                if result == "kill":
                    kill_triggered = True
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

    if not kill_triggered:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
        print(f"\n  [detector] Scan complete. Real: {len(real)} | Bots: {len(bots)}")
    else:
        print(
            f"\n  [detector] Stopped early. "
            f"Real: {len(real)} | Bots: {len(bots)} | "
            f"Remaining: {len(remaining) - len(scanned)}"
        )
        print("  Progress saved — re-run to continue from where you left off.")

    return real, bots
