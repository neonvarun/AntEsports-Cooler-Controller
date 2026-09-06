# Ant Esports Liquid Cooler Controller

A modern, lightweight, high-performance controller and digital pump display software for **Ant Esports AIO Liquid Coolers** (USB HID `VID: 0x5131`, `PID: 0x2007`).

Designed as a superior alternative to the OEM software, this application features a sleek dark UI, intelligent anti-blink temperature smoothing, customizable multi-metric telemetry cycles, and background system tray integration.

---

## Key Features

- **Modern Dark UI Dashboard**: Clean, responsive PyQt6 interface with real-time telemetry cards, system tray minimization, and background service execution.
- **Anti-Blink Temperature Smoothing**:
  - The stock cooler firmware blinks rapidly when temperatures reach >= 85°C.
  - Offers **Cap at 84°C** and **Linear Compression (75°C–100°C scaled to 75°C–84°C)** modes to keep the digits smooth and legible without flashing.
- **Auto Cycle Playlist & Duration Editor**:
  - Cycle through **CPU Temp**, **GPU Temp**, **CPU Load**, **GPU Load**, and **CPU Power**.
  - Customize individual display durations for each metric (e.g., 5s on CPU Temp, 3s on GPU Temp).
- **Configurable Polling Rates**: Select update intervals from 250ms, 500ms, 1000ms, 2000ms, to 3000ms.
- **Fahrenheit & Celsius Toggle**: Full hardware support for Fahrenheit and Celsius display modes.
- **Display Power Switch**: Toggle the pump digital LED display ON or OFF directly from the UI or system tray.
- **Low-Latency Sensor Engine**: Built-in C# LibreHardwareMonitor bridge (`lhm_bridge.exe`) for fast, accurate kernel-level sensor queries with fallback to psutil and WMI.
- **Stealth Windows Startup**: Option to run silently in the background on Windows boot via Task Scheduler / VBS launcher.

---

## Hardware Compatibility

- **Vendor ID (VID)**: `0x5131` (decimal `20785`)
- **Product ID (PID)**: `0x2007` (decimal `8199`)
- Compatible with Ant Esports ICE-Infinity / ICE-Flow and similar AIO coolers with 7-segment digital pump cap displays using the 5131:2007 HID controller.

---

## Installation & Setup

### 1. Prerequisites
- **Windows 10 / 11 (64-bit)**
- **Python 3.10+** (Python 3.11, 3.12, or 3.13 recommended)
- Administrator privileges (required by LibreHardwareMonitor to read motherboard and CPU temperature sensors).

### 2. Clone the Repository
```bash
git clone https://github.com/neonvarun/AntEsports-Cooler-Controller.git
cd AntEsports-Cooler-Controller
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the Application
To run with full hardware sensor access, launch using the provided launcher:
```bash
# Direct Python execution:
python main.py

# Or run as Administrator:
Run_As_Admin.bat
```

---

## Project Architecture

```
AntEsports-Cooler-Controller/
├── assets/                  # UI icons and graphical assets
├── bin/                     # LibreHardwareMonitorLib binaries & compiled bridge
│   ├── lhm_bridge.exe       # High-performance C# sensor daemon
│   └── LibreHardwareMonitorLib.dll
├── src/                     # Core Python application
│   ├── cooler_protocol.py   # 65-byte USB HID report encoder/decoder
│   ├── cooler_service.py    # Background telemetry polling thread
│   ├── config_manager.py    # JSON configuration persistence
│   ├── lhm_sensor_engine.py # Sensor orchestration and hardware fallbacks
│   └── ui/                  # PyQt6 UI components & cycle settings dialog
│       ├── main_window.py
│       └── cycle_settings_dialog.py
├── lhm_bridge.cs            # Source code for the C# LHM sensor bridge
├── main.py                  # Application entry point
├── requirements.txt         # Python package dependencies
└── Run_As_Admin.bat         # UAC elevated batch launcher
```

---

## License

This project is open-source and available under the [MIT License](LICENSE).
