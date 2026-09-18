@echo off
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\pythonw.exe" (set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe") else (set "PYTHONW=pythonw.exe")
start "" "%PYTHONW%" main.py
