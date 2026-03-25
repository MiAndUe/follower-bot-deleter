import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from auth import get_authenticated_client
from detector import scan_non_mutuals
from remover import remove_bots

load_dotenv()
logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s │ %(name)s │ %(message)s",
)

DATA_DIR = Path("data")
FOLLOWERS_FILE = DATA_DIR / "followers_1.json"
FOLLOWING_FILE = DATA_DIR / "following.json"
REAL_OUT = Path("real.json")
FAKE_OUT = Path("fake.json")


def _extract_usernames_from_export(filepath: Path, *, label: str) -> set[str]:
    if not filepath.exists():
        raise FileNotFoundError(
            f"  ✗  '{filepath}' not found.\n"
            f"     Drop your Instagram export files into the ./data/ directory."
        )

    raw = json.loads(filepath.read_text(encoding="utf-8"))
    usernames: set[str] = set()

    if isinstance(raw, list):
        entries = raw
    elif isinstance(raw, dict):
        entries = next(iter(raw.values()), [])
    else:
        raise ValueError(f"Unexpected JSON structure in {filepath}")

    for entry in entries:
        title = entry.get("title", "").strip()
        if title:
            usernames.add(title)
            continue
        for item in entry.get("string_list_data", []):
            value = item.get("value", "").strip()
            if value:
                usernames.add(value)

    print(f"  [phase 1] {label}: {len(usernames):,} accounts parsed from {filepath.name}")
    return usernames


def run_phase_1() -> set[str]:
    print("\n" + "═" * 60)
    print("  PHASE 1 — Local Data Parsing")
    print("═" * 60)

    followers = _extract_usernames_from_export(FOLLOWERS_FILE, label="Followers")
    following = _extract_usernames_from_export(FOLLOWING_FILE, label="Following")

    non_mutuals = followers - following
    mutuals = followers & following

    print(f"\n  Mutuals       : {len(mutuals):,}  (follow each other — skipped)")
    print(f"  Non-Mutuals   : {len(non_mutuals):,}  (follow you, you don't follow back)")
    print(f"  ➜  {len(non_mutuals):,} accounts will proceed to Phase 2.\n")

    return non_mutuals


def run_phase_2(client, non_mutuals: set[str]) -> tuple[list[dict], list[dict]]:
    print("\n" + "═" * 60)
    print("  PHASE 2 — Live Heuristic Scan")
    print("═" * 60)

    real, bots = scan_non_mutuals(client, non_mutuals)

    REAL_OUT.write_text(json.dumps(real, indent=2, ensure_ascii=False))
    FAKE_OUT.write_text(json.dumps(bots, indent=2, ensure_ascii=False))
    print(f"\n  [phase 2] Results written → {REAL_OUT} | {FAKE_OUT}")

    return real, bots


def _review_and_augment_bots(bots: list[dict]) -> list[str]:
    print("\n" + "═" * 60)
    print("  PHASE 3 — Verification & Removal")
    print("═" * 60)

    print(f"\n  Detected bots : {len(bots)}")
    if bots:
        print("\n  Flagged accounts:")
        for i, b in enumerate(bots, 1):
            priv = " [private]" if b.get("is_private") else ""
            print(
                f"    {i:>3}. @{b['username']:<28} "
                f"followers={b['follower_count']:>4}  "
                f"following={b['following_count']:>5}{priv}"
            )

    print(
        "\n  You may add extra usernames to the removal list now.\n"
        "  Enter one username per line (without @).\n"
        "  Press ENTER on an empty line when done.\n"
    )

    extra: list[str] = []
    while True:
        line = input("  Add username (or ENTER to continue): ").strip().lstrip("@")
        if not line:
            break
        extra.append(line)

    if extra:
        print(f"  Added {len(extra)} extra username(s): {', '.join('@' + u for u in extra)}")
        augmented = bots + [{"username": u, "manually_added": True} for u in extra]
        FAKE_OUT.write_text(json.dumps(augmented, indent=2, ensure_ascii=False))

    combined = [b["username"] for b in bots] + extra
    return combined


def _confirm_removal(usernames: list[str]) -> bool:
    if not usernames:
        print("\n  No accounts to remove. Exiting.")
        return False

    print(f"\n  ⚠️   About to remove {len(usernames)} follower(s) from your account.")
    print("  This action cannot be undone automatically.\n")
    answer = input("  Proceed? (y/n): ").strip().lower()
    return answer == "y"


def run_phase_3(client, bots: list[dict]) -> None:
    to_remove = _review_and_augment_bots(bots)

    if not _confirm_removal(to_remove):
        print("  Aborted. No accounts were removed.")
        return

    summary = remove_bots(client, to_remove)

    print("\n" + "═" * 60)
    print("  REMOVAL SUMMARY")
    print("═" * 60)
    print(f"  ✓  Successfully removed : {len(summary['removed'])}")
    print(f"  ✗  Failed / skipped     : {len(summary['failed'])}")

    if summary["failed"]:
        print(f"\n  Failed usernames:")
        for u in summary["failed"]:
            print(f"    • @{u}")

    result = {
        "removed": summary["removed"],
        "failed": summary["failed"],
    }
    Path("removal_report.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False)
    )
    print(f"\n  Full report saved → removal_report.json")


def main() -> None:
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║        Instagram Bot Guard  —  Data Export Edition       ║")
    print("╚══════════════════════════════════════════════════════════╝")

    try:
        non_mutuals = run_phase_1()
    except FileNotFoundError as exc:
        sys.exit(str(exc))

    if not non_mutuals:
        print("  No non-mutual followers found. Nothing to do.")
        sys.exit(0)

    print("\n" + "═" * 60)
    print("  AUTHENTICATION")
    print("═" * 60 + "\n")
    client = get_authenticated_client()

    _, bots = run_phase_2(client, non_mutuals)

    run_phase_3(client, bots)

    print("\n  Done. 👋\n")


if __name__ == "__main__":
    main()
