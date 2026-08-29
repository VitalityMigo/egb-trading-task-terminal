@echo off
REM Lance notify_daemon.py depuis le venv Python courant.
REM A double-cliquer, ou a lancer depuis un terminal ou le venv est deja active.
REM Si le venv n'est pas active automatiquement, decommente et adapte la ligne
REM ci-dessous pour pointer vers le python.exe de ton venv :
REM call "%~dp0.venv\Scripts\activate.bat"

cd /d "%~dp0"
python notify_daemon.py
pause
