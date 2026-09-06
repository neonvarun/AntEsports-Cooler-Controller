import os
import sys
import json
import winreg

class ConfigManager:
    APP_NAME = "AntEsportsCooler"
    
    DEFAULT_CONFIG = {
        "display_metric": "cpu_temp",
        "anti_blink_enabled": True,
        "anti_blink_mode": "cap_84",
        "temp_unit": "C",
        "temp_offset": 0,
        "alternating_interval_sec": 5,
        "update_interval_ms": 1000,
        "start_with_windows": False,
        "start_minimized": False,
        "close_to_tray": True,
        "startup_animation": True,
        "smooth_stepping": True,
        "cycle_playlist": ["cpu_temp", "gpu_temp", "cpu_power", "cpu_load"],
        "cycle_interval_sec": 5,
        "auto_game_mode": False,
        "auto_game_threshold_pct": 35,
        "desk_clock_enabled": False,
        "desk_clock_idle_sec": 300,
        "display_power_on": True
    }
    
    TASK_NAME = "AntEsportsICEStorm240_Autostart"

    def __init__(self):
        app_data = os.environ.get("APPDATA", os.path.expanduser("~"))
        self.config_dir = os.path.join(app_data, self.APP_NAME)
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.config = dict(self.DEFAULT_CONFIG)
        self.load()

    def load(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.config.update(saved)
            except Exception as e:
                print(f"[Config] Error loading config: {e}")
        else:
            self.save()

    def save(self):
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"[Config] Error saving config: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default if default is not None else self.DEFAULT_CONFIG.get(key))

    def set(self, key, value):
        self.config[key] = value
        self.save()
        if key in ("start_with_windows", "autostart"):
            self.set_autostart(bool(value))

    def set_autostart(self, enable):
        """Configure silent elevated autostart via Windows Task Scheduler with registry fallback."""
        import subprocess
        CREATE_NO_WINDOW = 0x08000000
        task_created = False

        # 1. Attempt Windows Task Scheduler task (succeeds when running elevated / as admin)
        try:
            if enable:
                proj_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                main_py = os.path.join(proj_dir, "main.py")
                pythonw = r"C:\Users\USER\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
                if not os.path.exists(pythonw):
                    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
                
                tr_cmd = f'"{pythonw}" "{main_py}" --minimized'
                cmd = [
                    "schtasks.exe", "/create",
                    "/tn", self.TASK_NAME,
                    "/tr", tr_cmd,
                    "/sc", "onlogon",
                    "/rl", "highest",
                    "/f"
                ]
                res = subprocess.run(cmd, creationflags=CREATE_NO_WINDOW, capture_output=True)
                task_created = (res.returncode == 0)
            else:
                cmd = ["schtasks.exe", "/delete", "/tn", self.TASK_NAME, "/f"]
                subprocess.run(cmd, creationflags=CREATE_NO_WINDOW, check=False)
        except Exception as e:
            print(f"[Config] Failed to update Task Scheduler: {e}")

        # 2. Registry fallback / cleanup
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE
            )
            if enable and not task_created:
                proj_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
                main_py = os.path.join(proj_dir, "main.py")
                pythonw = r"C:\Users\USER\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
                if not os.path.exists(pythonw):
                    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
                cmd = f'"{pythonw}" "{main_py}" --minimized'
                winreg.SetValueEx(key, self.APP_NAME, 0, winreg.REG_SZ, cmd)
            elif not enable or task_created:
                for val_name in [self.APP_NAME, "AntEsportsCooler"]:
                    try:
                        winreg.DeleteValue(key, val_name)
                    except FileNotFoundError:
                        pass
            winreg.CloseKey(key)
        except Exception:
            pass
