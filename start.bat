@echo off
cd /d "%~dp0"
if not defined GROQ_API_KEY (
  echo GROQ_API_KEY is not set in this terminal.
  echo Get a free key: https://console.groq.com/keys
  echo Then in this window run:
  echo   set GROQ_API_KEY=your_key_here
  echo Or permanently:
  echo   setx GROQ_API_KEY "your_key_here"
  echo Then open a NEW terminal and run this start.bat again.
  pause
  exit /b 1
)
echo Starting Groq Whisperer.
echo   Pause = press to start, press again to stop
echo   F8    = hold to talk, release to stop
echo Close this window to stop.
".\venv\Scripts\python.exe" main.py
if errorlevel 1 python main.py
pause
