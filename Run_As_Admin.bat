@echo off
:: Self-elevating launcher for Ant Esports ICEStorm-240 Controller
net session >nul 2>&1
if %errorLevel% == 0 (
    goto :admin
) else (
    echo Requesting Administrator privileges to access AMD Ryzen hardware registers...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)

:admin
cd /d "%~dp0"
title Ant Esports ICEStorm-240 Controller (Elevated)

start "" pythonw.exe main.py
