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
- **Low-Latency Sensor Engine**: Built-in x64 C# LibreHardwareMonitor 0.9.6 bridge using the signed PawnIO 2.2.0 hardware access backend, with psutil and NVML user-mode metrics.
- **Stealth Windows Startup**: Option to run silently in the background on Windows boot via Task Scheduler / VBS launcher.

The application has no HWiNFO dependency and does not use HWiNFO shared memory, registry settings, or processes. The first elevated launch verifies and installs the bundled signed PawnIO prerequisite when necessary. No runtime download is required.

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
- Administrator privileges (required once to install PawnIO and to read low-level motherboard and CPU temperature sensors).

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
Launch using the provided launcher. The first run may show a UAC prompt for the bundled PawnIO installation:
```bash
# Direct Python execution:
python main.py

# Or run as Administrator:
Run_As_Admin.bat
```

The application validates the PawnIO installer hash and Authenticode signature before installing it. It uses the installed PawnIO service through LibreHardwareMonitor and never enables test signing or Defender exclusions.

The native sensor bridge opens LibreHardwareMonitor only for the duration of each sample and closes it before the next interval. This releases the shared PCI and ISA access locks between samples so other hardware tools are not blocked by an idle dashboard.

To rebuild the bridge from source, restore `bridge\packages.config` with NuGet and build the x64 project with the .NET Framework MSBuild tooling. The project pins both the CLR 4-compatible LHM 0.9.6 package and the .NET Framework 4.7.2 reference assemblies. The checked-in `bin` copy is the same LHM runtime assembly used by the application, so running the application does not require NuGet or a network connection.

---

## Project Architecture

```
AntEsports-Cooler-Controller/
├── assets/                  # UI icons and graphical assets
├── bin/                     # LHM bridge dependencies and signed PawnIO installer
│   ├── lhm_bridge_pawnio.exe # High-performance C# sensor daemon
│   ├── LibreHardwareMonitorLib.dll
│   └── PawnIO_setup.exe
├── src/                     # Core Python application
│   ├── cooler_protocol.py   # 65-byte USB HID report encoder/decoder
│   ├── cooler_service.py    # Background telemetry polling thread
│   ├── config_manager.py    # JSON configuration persistence
│   ├── pawnio_manager.py    # Offline installer verification and migration
│   ├── sensor_engine.py     # LHM/PawnIO and user-mode sensor orchestration
│   └── ui/                  # PyQt6 UI components & cycle settings dialog
│       ├── main_window.py
│       └── cycle_settings_dialog.py
├── lhm_bridge.cs            # Source code for the C# LHM sensor bridge
├── bridge/                  # Reproducible x64 .NET Framework bridge project
├── LICENSES/                # Third-party license texts
├── main.py                  # Application entry point
├── requirements.txt         # Python package dependencies
└── Run_As_Admin.bat         # UAC elevated batch launcher
```

---

## License

This project is open-source and available under the [MIT License](LICENSE.txt).
