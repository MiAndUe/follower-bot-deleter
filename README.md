## How It Works

The tool runs in three phases.

**Phase 1 — Local Parsing**
It reads the two JSON files from your Instagram data export and compares your followers against the accounts you follow. Anyone you follow back is immediately skipped — they are never flagged. Only followers you do not follow back proceed to the next phase.

**Phase 2 — Live Scan**
For each remaining follower, the tool fetches their live profile stats from Instagram. An account is flagged as a likely bot if it has fewer than 50 followers and is following more than 1000 accounts (this can be changed in detector.py, I based it on the bots that follow me). Results are saved to disk after every single account, so you can stop and resume at any time without losing progress.

**Phase 3 — Review & Removal**
The tool displays all flagged accounts and lets you add or remove anyone from the list manually before anything is deleted. A final confirmation prompt is shown before any removals are made.

---

## Project Structure

```
follower-bot-deleter/
├── data/                  # Place your Instagram export files here (see below)
│   ├── followers_1.json
│   └── following.json
├── main.py                # Entry point — runs all three phases
├── auth.py                # Session-based login
├── detector.py            # Live profile scanning and bot detection
├── remover.py             # Follower removal
├── requirements.txt       # Dependencies
├── .env.example           # Credential template
└── .gitignore
```

---

## Setup & Installation

**Requirements:** Python 3.10 or higher.

**1. Clone the repository**
```bash
git clone https://github.com/your-username/follower-bot-deleter.git
cd follower-bot-deleter
```

**2. Create and activate a virtual environment**
```bash
python -m venv venv
```
On Windows:
```bash
venv\Scripts\activate
```
On Mac/Linux:
```bash
source venv/bin/activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Set up your credentials**

Copy `.env.example` to a new file called `.env` and fill in your Instagram username and password:
```
INSTAGRAM_USERNAME=your_handle
INSTAGRAM_PASSWORD=your_password
```

**5. Get your Instagram data export**

- Go to Instagram → **Settings** → **Your activity** → **Download your information**
- Select **Download or transfer information** → your account → **Some of your information**
- Check **Followers and following** → **Download to device**
- Set the format to **JSON** (not HTML)
- Instagram will email you a download link — this can take a few minutes to a few hours
- Unzip the download and find these two files inside the `followers_and_following/` folder:
  - `followers_1.json`
  - `following.json`
- Copy both files into the `data/` folder in this project

---

## Usage / How to Run

With your virtual environment activated, run:

```bash
python main.py
```

The tool will walk you through each phase automatically. At the end of Phase 2 you can stop and re-run at any time — it will resume from where it left off.

If this is your first run, you will be prompted to log in with your Instagram credentials. A `session.json` file will be saved so you are not asked to log in again on future runs.

---

## Configuration / Tunables

All tunables are at the top of `detector.py`:

| Setting | Default | Description |
|---|---|---|
| `BOT_MAX_FOLLOWERS` | `50` | Accounts with fewer followers than this are candidates |
| `BOT_MIN_FOLLOWING` | `1000` | Accounts following more than this are candidates |
| `MAX_WORKERS` | `4` | Number of accounts scanned in parallel |
| `DELAY_MIN` | `2.0` | Minimum seconds between requests per worker |
| `DELAY_MAX` | `5.0` | Maximum seconds between requests per worker |

And in `remover.py`:

| Setting | Default | Description |
|---|---|---|
| `DELAY_MIN` | `6.0` | Minimum seconds between removals |
| `DELAY_MAX` | `12.0` | Maximum seconds between removals |

Increasing `MAX_WORKERS` speeds up the scan but increases the risk of hitting Instagram's rate limit. Going above 5 workers or below 2 seconds delay is not recommended.

---

## Disclaimer / ToS Warning

> **Use at your own risk.**

Automating actions on Instagram using third-party tools violates [Instagram's Terms of Service](https://help.instagram.com/581066165581870). Your account could be flagged, restricted, or banned. The rate-limiting and delay logic in this tool reduces but does not eliminate that risk.

This tool was built for personal use on a single account. It is not intended for bulk or commercial use. The author takes no responsibility for any consequences to your account.
