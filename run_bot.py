"""Supervisor: keeps bot.py running without any Claude session.

- waits until the phone shows up in adb
- restarts bot.py if it crashes or hangs (no log output for HANG_SEC)
- STOPS for good on: out of gold / no mission reward left (exit 3) and on a
  detected payment screen (exit 4).  It never buys anything.

usage: python run_bot.py          (or double-click start_bot.bat)
logs : logs/bot_YYYYMMDD.log, decisions in logs/decisions.csv
"""
import datetime
import subprocess
import sys
import time
from pathlib import Path

import adb

ROOT = Path(__file__).parent
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)
HANG_SEC = 300
STOP_CODES = {3: "OUT OF GOLD (refills + mission rewards used up)",
              4: "PAYMENT SCREEN DETECTED"}


def log(msg):
    line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with (LOGS / "supervisor.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def device_ready():
    """`adb devices` -> True when a device is in the 'device' state.

    Output goes to a temp file, not a pipe: when adb has to (re)start its server,
    the daemon inherits the pipe and subprocess.run(timeout=...) then blocks forever."""
    import tempfile
    try:
        with tempfile.TemporaryFile("w+", encoding="utf-8", errors="ignore") as f:
            p = subprocess.Popen([adb.ADB, "devices"], stdout=f, stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL)
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
                return False
            f.seek(0)
            return any(l.endswith("	device") for l in f.read().splitlines())
    except Exception:
        return False


def run_once():
    path = LOGS / f"bot_{datetime.date.today():%Y%m%d}.log"
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n===== start {datetime.datetime.now():%H:%M:%S} =====\n")
        f.flush()
        p = subprocess.Popen([sys.executable, "-u", str(ROOT / "bot.py"), "0"],
                             stdout=f, stderr=subprocess.STDOUT, cwd=ROOT)
        last_size, last_change = path.stat().st_size, time.time()
        while p.poll() is None:
            time.sleep(10)
            size = path.stat().st_size
            if size != last_size:
                last_size, last_change = size, time.time()
            elif time.time() - last_change > HANG_SEC:
                log(f"no log output for {HANG_SEC}s -> killing hung bot")
                p.kill()
                break
        return p.wait()


def main():
    log("supervisor started")
    while True:
        while not device_ready():
            log("phone not found in adb - waiting (check USB / scrcpy)")
            time.sleep(15)
        code = run_once()
        if code in STOP_CODES:
            log(f"stopped for good: {STOP_CODES[code]}")
            return code
        log(f"bot exited with code {code} -> restart in 5s")
        time.sleep(5)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("stopped by user")
