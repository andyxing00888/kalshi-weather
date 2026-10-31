"""Long-running driver for GitHub Actions: GitHub drops many scheduled runs, so one job loops instead.

  python3 paper/cron.py [hours]   run the hourly tasks now and then at :05 each hour for `hours`
                                  (0 = once), the daily tasks once per UTC day after DAILY_HOUR,
                                  committing and pushing after every pass
A failing task is reported and skipped; it never stops the loop.
"""
import os, subprocess, sys, time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOURLY = ["python3 paper/trader.py log", "python3 consistency.py log", "python3 lip.py track", "python3 xvenue.py log"]
DAILY = ["python3 paper/trader.py score", "python3 paper/report.py",
         "mkdir -p data && python3 lip.py 300 && python3 lip.py watch"]
DAILY_HOUR = 15
MINUTE = 5


def sh(cmd):
    print(f"$ {cmd}", flush=True)
    r = subprocess.run(cmd, shell=True, cwd=ROOT)
    if r.returncode:
        print(f"! exit {r.returncode}: {cmd}", flush=True)
    return r.returncode == 0


def commit():
    sh("git add paper/data paper/reports README.md docs")
    if subprocess.run("git diff --cached --quiet", shell=True, cwd=ROOT).returncode == 0:
        return
    sh(f'git commit -q -m "paper: {datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ}"')
    for _ in range(3):
        if sh("git pull -q --rebase && git push -q"):
            return
        time.sleep(10)


def daily_due(now):
    return now.hour >= DAILY_HOUR and not os.path.exists(os.path.join(ROOT, "paper", "reports", f"{now:%Y-%m-%d}.md"))


def one_pass():
    for cmd in HOURLY:
        sh(cmd)
    now = datetime.now(timezone.utc)
    if daily_due(now):
        for cmd in DAILY:
            sh(cmd)
    commit()


def main():
    budget = float(sys.argv[1]) * 3600 if len(sys.argv) > 1 else 0
    start = time.time()
    while True:
        one_pass()
        now = time.time()
        wait = (MINUTE * 60 - now % 3600) % 3600 or 3600
        if now + wait - start > budget:
            return
        print(f"sleeping {wait / 60:.0f} min", flush=True)
        time.sleep(wait)


if __name__ == "__main__":
    main()
