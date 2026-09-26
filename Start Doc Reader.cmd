@echo off
rem Tro ly doc tai lieu. Keo tha mot file len day de mo ngay file do.
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -X utf8 doc_reader.py %*
) else (
  echo Chua co moi truong Python. Chay lan luot:
  echo   python -m venv .venv
  echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
)
