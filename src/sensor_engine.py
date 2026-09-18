import ctypes
import json
import os
import psutil
import subprocess
import sys
import threading
import time

from .pawnio_manager import PawnIOManager, PawnIOStatus


def is_admin_user():
    """Check if the current process has Windows Administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def restart_as_admin():
    """Restart the current Python application with Administrator privileges via UAC."""
    try:
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        executable = sys.executable
        cmd_args = f'"{script}" {params}'.strip()
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, cmd_args, None, 1
        )
        if ret > 32:
            sys.exit(0)
        return False
    except Exception as exc:
        print(f"[SensorEngine] Failed to elevate: {exc}")
        return False


class HardwareData:
    def __init__(self):
        self.cpu_name = "AMD Ryzen 9 7900X"
        self.cpu_temp = 0.0
        self.cpu_load = 0.0
        self.cpu_clock = 0
        self.cpu_fan = 0
        self.cpu_power = 0.0

        self.gpu_name = "Graphics Card"
        self.gpu_temp = 0.0
        self.gpu_load = 0.0
        self.gpu_clock = 0
        self.gpu_fan = 0
        self.gpu_power = 0.0

        self.ram_load = 0.0
        self.ram_used_mb = 0
        self.ram_total_mb = 0

        self.disk_load = 0.0
        self.disk_total_gb = 0
        self.is_sensor_real = False
        self.is_admin = False
        self.sensor_source = "Initializing..."
        self.sensor_backend_status = PawnIOStatus.MISSING.value


class NvmlReader:
    """Direct ctypes interface to NVIDIA Management Library (nvml.dll)."""

    def __init__(self):
        self.available = False
        self.handle = None
        self.device_name = "NVIDIA GeForce"
        try:
            dll_path = os.path.expandvars(r"%SystemRoot%\System32\nvml.dll")
            if not os.path.exists(dll_path):
                dll_path = "nvml.dll"
            self.nvml = ctypes.CDLL(dll_path)

            if self.nvml.nvmlInit_v2() == 0:
                handle = ctypes.c_void_p()
                if self.nvml.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(handle)) == 0:
                    self.handle = handle
                    self.available = True
                    try:
                        name_buf = ctypes.create_string_buffer(96)
                        if self.nvml.nvmlDeviceGetName(handle, name_buf, 96) == 0:
                            self.device_name = name_buf.value.decode("utf-8", errors="ignore")
                    except Exception:
                        pass
        except Exception:
            self.available = False

    def read_gpu(self):
        if not self.available or not self.handle:
            return None
        try:
            temp = ctypes.c_uint()
            self.nvml.nvmlDeviceGetTemperature(self.handle, 0, ctypes.byref(temp))

            class NvmlUtilization(ctypes.Structure):
                _fields_ = [("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]

            util = NvmlUtilization()
            self.nvml.nvmlDeviceGetUtilizationRates(self.handle, ctypes.byref(util))

            clock = ctypes.c_uint()
            self.nvml.nvmlDeviceGetClockInfo(self.handle, 0, ctypes.byref(clock))

            fan = ctypes.c_uint()
            try:
                self.nvml.nvmlDeviceGetFanSpeed(self.handle, ctypes.byref(fan))
                fan_val = fan.value
            except Exception:
                fan_val = 0

            power = ctypes.c_uint()
            try:
                self.nvml.nvmlDeviceGetPowerUsage(self.handle, ctypes.byref(power))
                power_w = power.value / 1000.0
            except Exception:
                power_w = 0.0

            return {
                "name": self.device_name,
                "gpu_temp": float(temp.value),
                "gpu_load": float(util.gpu),
                "gpu_clock": int(clock.value),
                "gpu_fan": int(fan_val),
                "gpu_power": float(power_w),
            }
        except Exception:
            return None

    def close(self):
        self.available = False
        self.handle = None


class SensorEngine:
    def __init__(self, bridge_path=None, pawnio_manager=None):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if bridge_path is None:
            bridge_path = os.path.join(base_dir, "bin", "lhm_bridge.exe")
        self.bridge_path = bridge_path

        self.data = HardwareData()
        self.running = False
        self.bridge_process = None
        self.thread = None
        self.bridge_thread = None
        self.lock = threading.Lock()

        self.nvml = NvmlReader()
        self.pawnio = pawnio_manager or PawnIOManager(base_dir)
        self.pawnio_status = PawnIOStatus.MISSING
        self._last_lhm_data = {}
        self._last_bridge_error = ""
        self.is_admin = is_admin_user()

    def start(self):
        if self.running:
            return
        self.running = True

        try:
            self.pawnio_status = self.pawnio.ensure_ready()
        except Exception as exc:
            self.pawnio_status = PawnIOStatus.INSTALL_FAILED
            self._last_bridge_error = f"PawnIO prerequisite check failed: {exc}"
            print(f"[SensorEngine] {self._last_bridge_error}")
        if self.pawnio_status != PawnIOStatus.READY:
            detail = getattr(self.pawnio, "last_detail", "")
            print(f"[SensorEngine] PawnIO status: {self.pawnio_status.value}. {detail}".strip())

        if os.path.exists(self.bridge_path):
            try:
                self.bridge_process = subprocess.Popen(
                    [self.bridge_path, "--loop", "1000"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                self.bridge_thread = threading.Thread(
                    target=self._read_bridge_output,
                    name="LhmBridgeReader",
                    daemon=True,
                )
                self.bridge_thread.start()
            except Exception as exc:
                self._last_bridge_error = str(exc)
                print(f"[SensorEngine] Failed to start native hardware bridge: {exc}")
        else:
            self._last_bridge_error = f"Bridge not found: {self.bridge_path}"
            print(f"[SensorEngine] {self._last_bridge_error}")

        self.thread = threading.Thread(
            target=self._update_loop,
            name="SensorEngine",
            daemon=True,
        )
        self.thread.start()

    def stop(self):
        self.running = False
        process = self.bridge_process
        self.bridge_process = None
        if process:
            try:
                process.terminate()
                process.wait(timeout=1.5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        if self.nvml:
            self.nvml.close()

    def _read_bridge_output(self):
        process = self.bridge_process
        if not process or not process.stdout:
            return
        while self.running:
            line = process.stdout.readline()
            if not line:
                break
            line = line.strip()
            if not line.startswith("{") or not line.endswith("}"):
                continue
            try:
                parsed = json.loads(line)
                with self.lock:
                    if "error" in parsed:
                        self._last_bridge_error = str(parsed.get("error", ""))
                    else:
                        self._last_lhm_data = parsed
                        self._last_bridge_error = ""
            except (TypeError, ValueError):
                continue

    @staticmethod
    def _number(value, default=0.0):
        try:
            number = float(value)
            if number != number or number in (float("inf"), float("-inf")):
                return default
            return number
        except (TypeError, ValueError):
            return default

    def _status_text(self, cpu_temp):
        valid_temp = 15.0 < cpu_temp < 125.0
        if self.pawnio_status == PawnIOStatus.READY:
            if valid_temp:
                return "LibreHardwareMonitor + PawnIO"
            if not self.is_admin:
                return "PawnIO requires Administrator"
            return "PawnIO active; waiting for CPU telemetry"
        if self.pawnio_status == PawnIOStatus.NOT_ELEVATED:
            status = "PawnIO requires Administrator"
        elif self.pawnio_status == PawnIOStatus.REBOOT_REQUIRED:
            status = "Restart required for PawnIO"
        elif self.pawnio_status in (PawnIOStatus.LEGACY_BLOCKED, PawnIOStatus.LEGACY_CLEANUP_FAILED):
            status = "Legacy sensor cleanup blocked"
        elif self.pawnio_status == PawnIOStatus.INSTALL_FAILED:
            status = "PawnIO installation failed"
        elif self.pawnio_status == PawnIOStatus.INVALID_PACKAGE:
            status = "PawnIO package validation failed"
        else:
            status = "PawnIO unavailable"

        detail = " ".join(str(getattr(self.pawnio, "last_detail", "")).split())
        if detail:
            return f"{status}: {detail[:160]}"
        return status

    def _update_loop(self):
        while self.running:
            try:
                self.is_admin = is_admin_user()

                cpu_load = self._number(psutil.cpu_percent(interval=None))
                cpu_freq_info = psutil.cpu_freq()
                cpu_clock = int(cpu_freq_info.current) if cpu_freq_info else 0

                mem = psutil.virtual_memory()
                ram_load = self._number(mem.percent)
                ram_used_mb = int(mem.used / (1024 * 1024))
                ram_total_mb = int(mem.total / (1024 * 1024))

                try:
                    disk = psutil.disk_usage("C:\\")
                    disk_load = self._number(disk.percent)
                    disk_total_gb = int(disk.total / (1024 * 1024 * 1024))
                except Exception:
                    disk_load = 0.0
                    disk_total_gb = 0

                with self.lock:
                    lhm = dict(self._last_lhm_data)

                lhm_cpu_temp = self._number(lhm.get("cpu_temp"))
                lhm_cpu_fan = int(self._number(lhm.get("cpu_fan")))
                lhm_cpu_power = self._number(lhm.get("cpu_power"))
                lhm_cpu_clock = int(self._number(lhm.get("cpu_clock")))

                cpu_temp = lhm_cpu_temp if 15.0 < lhm_cpu_temp < 125.0 else 0.0
                is_real = cpu_temp > 0.0
                if lhm_cpu_clock > 0:
                    cpu_clock = lhm_cpu_clock

                gpu_temp = self._number(lhm.get("gpu_temp"))
                gpu_load = self._number(lhm.get("gpu_load"))
                gpu_clock = int(self._number(lhm.get("gpu_clock")))
                gpu_fan = int(self._number(lhm.get("gpu_fan")))
                gpu_power = self._number(lhm.get("gpu_power"))
                gpu_name = str(lhm.get("gpu_name") or "Graphics Card")
                cpu_name = str(lhm.get("cpu_name") or "Unknown CPU")

                nvml_data = self.nvml.read_gpu()
                if nvml_data:
                    gpu_temp = nvml_data["gpu_temp"]
                    gpu_load = nvml_data["gpu_load"]
                    gpu_clock = nvml_data["gpu_clock"]
                    gpu_fan = nvml_data["gpu_fan"]
                    gpu_power = nvml_data["gpu_power"]
                    gpu_name = nvml_data["name"]

                with self.lock:
                    self.data.cpu_name = cpu_name
                    self.data.cpu_temp = cpu_temp
                    self.data.cpu_load = cpu_load
                    self.data.cpu_clock = cpu_clock
                    self.data.cpu_fan = lhm_cpu_fan
                    self.data.cpu_power = lhm_cpu_power

                    self.data.gpu_name = gpu_name
                    self.data.gpu_temp = gpu_temp
                    self.data.gpu_load = gpu_load
                    self.data.gpu_clock = gpu_clock
                    self.data.gpu_fan = gpu_fan
                    self.data.gpu_power = gpu_power

                    self.data.ram_load = ram_load
                    self.data.ram_used_mb = ram_used_mb
                    self.data.ram_total_mb = ram_total_mb
                    self.data.disk_load = disk_load
                    self.data.disk_total_gb = disk_total_gb
                    self.data.is_sensor_real = is_real
                    self.data.is_admin = self.is_admin
                    self.data.sensor_source = self._status_text(cpu_temp)
                    self.data.sensor_backend_status = self.pawnio_status.value
            except Exception as exc:
                print(f"[SensorEngine] Update error: {exc}")

            time.sleep(1.0)

    def get_snapshot(self):
        with self.lock:
            snap = HardwareData()
            snap.cpu_name = self.data.cpu_name
            snap.cpu_temp = self.data.cpu_temp
            snap.cpu_load = self.data.cpu_load
            snap.cpu_clock = self.data.cpu_clock
            snap.cpu_fan = self.data.cpu_fan
            snap.cpu_power = self.data.cpu_power
            snap.gpu_name = self.data.gpu_name
            snap.gpu_temp = self.data.gpu_temp
            snap.gpu_load = self.data.gpu_load
            snap.gpu_clock = self.data.gpu_clock
            snap.gpu_fan = self.data.gpu_fan
            snap.gpu_power = self.data.gpu_power
            snap.ram_load = self.data.ram_load
            snap.ram_used_mb = self.data.ram_used_mb
            snap.ram_total_mb = self.data.ram_total_mb
            snap.disk_load = self.data.disk_load
            snap.disk_total_gb = self.data.disk_total_gb
            snap.is_sensor_real = self.data.is_sensor_real
            snap.is_admin = self.data.is_admin
            snap.sensor_source = self.data.sensor_source
            snap.sensor_backend_status = self.data.sensor_backend_status
            return snap
