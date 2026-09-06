@echo off
title Ant Esports ICEStorm-240 Controller
cd /d "%~dp0"

:: Check for Administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [Ant Esports] Elevating to Administrator for hardware telemetry sync...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: Ensure the official Bitdefender-trusted R0ANTESPORTS kernel driver is running
sc start R0ANTESPORTS >nul 2>&1

:: Disable the legacy Ant Esports startup scheduled task so it never conflicts
schtasks /change /tn "ANTESPORTSStartupTaskOKver---ABCDEF6543A7" /disable >nul 2>&1

:: Terminate old Ant Esports binaries if running to claim the USB cooler HID port
taskkill /f /im ANTESPORTS.exe >nul 2>&1
taskkill /f /im allComputerInfoGetPro.exe >nul 2>&1

:: Ensure HWiNFO SharedMemorySupport is enabled in registry for hybrid sync
reg add "HKCU\Software\HWiNFO64" /v SharedMemorySupport /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKCU\Software\HWiNFO64\Sensors" /v SharedMemorySupport /t REG_DWORD /d 1 /f >nul 2>&1

:: Start the modern SaaS Control Center in background
start "" "pythonw.exe" "main.py"
