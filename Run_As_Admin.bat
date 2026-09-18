@echo off
:: Self-elevating launcher for Ant Esports ICEStorm-240 Controller
net session >nul 2>&1
if %errorLevel% == 0 (
    goto :admin
) else (
    echo Requesting Administrator privileges for hardware telemetry...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)

:admin
cd /d "%~dp0"
title Ant Esports ICEStorm-240 Controller (Elevated)
if exist "%~dp0.venv\Scripts\pythonw.exe" (set "PYTHONW=%~dp0.venv\Scripts\pythonw.exe") else (set "PYTHONW=pythonw.exe")

start "" "%PYTHONW%" main.py
