2. Setup steps on Windows
   - Install Python + psutil

In Command Prompt:

- python -m pip install psutil

b: Test manually first

From the folder where you saved game_guard.py:

cd C:\Users\<YOUR_USERNAME>\Documents\game_guard
python game_guard.py --games "yourgame.exe"

multiple games
python game_guard.py --games "eldenring.exe" "factorio.exe"

3. Make it run at startup via Task Scheduler

Press Win + R, type taskschd.msc, Enter.

In the right pane, click Create Task….

General tab:

Name: Game Guard

Check:

“Run whether user is logged on or not”

“Run with highest privileges”

Configure for: Windows 10

Triggers tab:

New…

Begin the task: At log on

Any user (or just your account)

OK

Actions tab:

New…

Action: Start a program

Program/script: full path to python.exe, e.g.:

C:\Users\<YOUR_USERNAME>\AppData\Local\Programs\Python\Python312\python.exe

(You can find it via where python in Command Prompt.)

Add arguments:

"C:\Users\<YOUR_USERNAME>\Documents\game_guard.py" --games "eldenring.exe" "anothergame.exe"

Start in:

C:\Users\<YOUR_USERNAME>\Documents

Click OK.

Settings tab:

“If the task is already running, then the following rule applies” → Do not start a new instance.

Uncheck “Stop the task if it runs longer than…” so it can run indefinitely.

Click OK, enter your password.

Now it’ll silently run every time Windows starts, watching those game processes, with no pause/quit/override unless you explicitly go into Task Manager / Task Scheduler and kill or edit it.
