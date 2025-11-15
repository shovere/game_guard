import os
import sys
import time
import random
import argparse
import datetime as dt

import psutil
from tkinter import Tk, messagebox


# --------------- CONFIG ---------------

CHECK_INTERVAL_SECONDS = 5

# Allowed hours (local time)
WEEKDAY_ALLOWED_START_HOUR = 19   # 7pm
WEEKDAY_ALLOWED_END_HOUR   = 23   # 11pm
WEEKEND_ALLOWED_START_HOUR = 10   # 10am
WEEKEND_ALLOWED_END_HOUR   = 23   # 11pm

# Daily playtime reminder
WEEKDAY_LIMIT_HOURS = 2
WEEKEND_LIMIT_HOURS = 3

# Outside-hours shutdown warning
OUTSIDE_HOURS_WARNING_MINUTES = 15

# Positive alternatives
POSITIVE_ALTERNATIVES = [
    "Call or text a friend to catch up",
    "Go for a 10–20 minute walk outside",
    "Do a quick 10-minute workout or stretch",
    "Take a short nap to reset",
    "Meditate for 5–10 minutes",
    "Clean or organize one small area",
    "Read a few pages of a book",
    "Listen to music or a podcast",
    "Write down what's on your mind",
    "Make a snack and drink water",
    "Take a shower",
    "Plan tomorrow's tasks",
]

ALTERNATIVE_GAMES = [
    "Stardew Valley",
    "Slay the Spire",
    "Tetris",
    "Mini Metro",
    "Dorfromantik",
]

# ------------- END CONFIG -------------

if ALTERNATIVE_GAMES:
    POSITIVE_ALTERNATIVES.append(
        "Try one of these low-stress games instead: " + ", ".join(ALTERNATIVE_GAMES)
    )


# ---------------- UTILITIES ----------------

def is_weekend(now: dt.datetime) -> bool:
    return now.weekday() >= 5  # Monday=0, Sunday=6


def is_allowed_now(now: dt.datetime) -> bool:
    hour = now.hour
    if is_weekend(now):
        return WEEKEND_ALLOWED_START_HOUR <= hour < WEEKEND_ALLOWED_END_HOUR
    else:
        return WEEKDAY_ALLOWED_START_HOUR <= hour < WEEKDAY_ALLOWED_END_HOUR


def daily_limit_seconds(now: dt.datetime) -> int:
    if is_weekend(now):
        return int(WEEKEND_LIMIT_HOURS * 3600)
    else:
        return int(WEEKDAY_LIMIT_HOURS * 3600)


def allowed_window_description(now: dt.datetime) -> str:
    if is_weekend(now):
        return "10:00–23:00 (Sat–Sun)"
    else:
        return "19:00–23:00 (Mon–Fri)"


def show_popup(title: str, message: str) -> None:
    root = Tk()
    root.withdraw()
    messagebox.showwarning(title, message)
    root.destroy()


def pick_positive_options() -> str:
    count = min(5, len(POSITIVE_ALTERNATIVES))
    picked = random.sample(POSITIVE_ALTERNATIVES, count)
    return "\n".join("• " + p for p in picked)


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    mins = seconds // 60
    hrs = mins // 60
    mins = mins % 60
    if hrs > 0:
        return f"{hrs}h {mins}m"
    return f"{mins} minutes"


# ---------------- LOGGING SYSTEM ----------------

def get_log_dir() -> str:
    """Logs go into game_guard/logs/ next to this script."""
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(folder, exist_ok=True)
    return folder


def log_path_for_date(date: dt.date) -> str:
    return os.path.join(get_log_dir(), f"{date.isoformat()}.log")


def log_path_for_today() -> str:
    return log_path_for_date(dt.date.today())


def log_line(text: str) -> None:
    """Append a timestamped line to today's log."""
    ts = dt.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {text}\n"
    with open(log_path_for_today(), "a", encoding="utf-8") as f:
        f.write(line)


def weekly_seconds_for_games(watched_games) -> int:
    """
    Sum DurationSeconds for all watched games from logs
    for the current week (Monday–Sunday).
    """
    log_dir = get_log_dir()
    if not os.path.isdir(log_dir):
        return 0

    # Week starts Monday (weekday 0)
    today = dt.date.today()
    week_start = today - dt.timedelta(days=today.weekday())  # Monday
    week_end = today  # inclusive

    watched_lower = {g.lower() for g in watched_games}
    total_seconds = 0

    for name in os.listdir(log_dir):
        if not name.endswith(".log"):
            continue
        try:
            date_part = name[:-4]  # strip .log
            file_date = dt.date.fromisoformat(date_part)
        except ValueError:
            continue

        if not (week_start <= file_date <= week_end):
            continue

        path = os.path.join(log_dir, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Expect format like:
                    # [HH:MM:SS] ENDED: EldenRing.exe — DurationSeconds: 4380
                    if "ENDED:" in line and "DurationSeconds:" in line:
                        #  Find game name & seconds
                        #  Example slice:
                        #  "[20:15:48] ENDED: EldenRing.exe — DurationSeconds: 4380"
                        try:
                            after_ended = line.split("ENDED:", 1)[1].strip()
                            # after_ended: "EldenRing.exe — DurationSeconds: 4380"
                            game_part, seconds_part = after_ended.split("DurationSeconds:", 1)
                            game_name = game_part.split("—", 1)[0].strip()
                            if game_name.lower() not in watched_lower:
                                continue
                            sec_str = seconds_part.strip()
                            sec_val = int(sec_str)
                            total_seconds += sec_val
                        except Exception:
                            continue
        except OSError:
            continue

    return total_seconds


# ---------------- GAME CHECKING ----------------

def find_running_game(watched_exes):
    targets = {g.lower(): g for g in watched_exes}
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info["name"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if not name:
            continue
        if name.lower() in targets:
            return targets[name.lower()], name
    return None, None


# ---------------- MAIN GUARD LOOP ----------------

def guard_loop(watched_games):
    print(f"[GameGuard] Watching: {', '.join(watched_games)}")

    session_active = False
    current_game_display = None
    session_start_time = None
    outside_warning_start = None

    last_check_time = dt.datetime.now()

    # Daily counters (reset each midnight)
    today_date = last_check_time.date()
    daily_play_seconds = 0.0
    daily_limit_reminder_shown = False

    while True:
        now = dt.datetime.now()

        # New day rollover
        if now.date() != today_date:
            today_date = now.date()
            daily_play_seconds = 0.0
            daily_limit_reminder_shown = False
            log_line("===== NEW DAY =====")

        # Add elapsed playtime if session active
        if session_active:
            daily_play_seconds += (now - last_check_time).total_seconds()

        display_name, exe_name = find_running_game(watched_games)
        game_running = display_name is not None

        allowed_now = is_allowed_now(now)
        weekend = is_weekend(now)
        daily_limit = daily_limit_seconds(now)
        allowed_window = allowed_window_description(now)

        # ----------- GAME START ------------
        if game_running and not session_active:
            session_active = True
            current_game_display = display_name
            session_start_time = now
            outside_warning_start = None

            log_line(f"STARTED: {display_name}")

            # Compute weekly total across all watched games
            week_secs = weekly_seconds_for_games(watched_games)
            week_str = format_duration(week_secs)

            weekly_line = f"So far this week you've played these games for about {week_str}."

            # Popup with weekly info + positive alternatives
            if allowed_now:
                limit_hours = WEEKEND_LIMIT_HOURS if weekend else WEEKDAY_LIMIT_HOURS
                msg = (
                    f"You've started {display_name} during allowed hours.\n\n"
                    f"Daily limit: {limit_hours} hours.\n"
                    f"{weekly_line}\n\n"
                    f"{pick_positive_options()}"
                )
                show_popup("Game Allowed", msg)
            else:
                outside_warning_start = now
                msg = (
                    f"You started {display_name} outside allowed hours.\n\n"
                    f"Allowed: {allowed_window}\n"
                    f"Shutdown in {OUTSIDE_HOURS_WARNING_MINUTES} minutes if not closed.\n\n"
                    f"{weekly_line}\n\n"
                    f"{pick_positive_options()}"
                )
                show_popup("Outside Allowed Hours", msg)
                log_line(f"WARNING: {display_name} started outside allowed hours.")

        # ----------- GAME RUNNING LOGIC ------------
        if game_running:

            # Outside-hours enforcement
            if not allowed_now:
                label = current_game_display or display_name
                if outside_warning_start is None:
                    outside_warning_start = now
                    msg = (
                        f"{label} is running outside allowed hours.\n\n"
                        f"Allowed: {allowed_window}\n"
                        f"Shutdown in {OUTSIDE_HOURS_WARNING_MINUTES} minutes.\n\n"
                        f"{pick_positive_options()}"
                    )
                    show_popup("Outside Allowed Hours", msg)
                    log_line(f"WARNING repeated: {label} still running outside hours.")

                elapsed = (now - outside_warning_start).total_seconds()
                if elapsed > OUTSIDE_HOURS_WARNING_MINUTES * 60:
                    log_line(f"SHUTDOWN TRIGGERED: {label} outside hours.")
                    os.system("shutdown /s /t 0")
                    return

            # Daily limit reminder
            elif not daily_limit_reminder_shown and daily_play_seconds >= daily_limit:
                played_hours_str = format_duration(daily_play_seconds)
                label = current_game_display or display_name
                msg = (
                    f"You've played {label} for {played_hours_str} today.\n\n"
                    f"Daily limit reached.\n\n"
                    f"{pick_positive_options()}"
                )
                show_popup("Daily Limit Reached", msg)
                daily_limit_reminder_shown = True
                log_line(f"REMINDER: Daily limit reached for {label} ({played_hours_str}).")

        # ----------- GAME STOP ------------
        if not game_running and session_active:
            session_active = False
            end_time = dt.datetime.now()
            duration = (end_time - session_start_time).total_seconds()
            duration_str = format_duration(duration)
            log_line(f"ENDED: {current_game_display} — DurationSeconds: {int(duration)} ({duration_str})")
            current_game_display = None
            session_start_time = None
            outside_warning_start = None

        last_check_time = now
        time.sleep(CHECK_INTERVAL_SECONDS)


# ---------------- CLI ----------------

def parse_args():
    parser = argparse.ArgumentParser(description="GameGuard – personal game-limiting tool.")
    parser.add_argument(
        "--games",
        "-g",
        nargs="+",
        required=True,
        help="Game executables to watch (e.g. eldenring.exe factorio.exe)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    guard_loop(args.games)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_line("Session terminated manually.")
        sys.exit(0)
