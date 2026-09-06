import time
import threading
import ctypes
from PyQt6.QtCore import QObject, pyqtSignal

from .sensor_engine import SensorEngine, HardwareData
from .cooler_protocol import CoolerProtocol, AntiBlinkMode, DisplayMetric, TemperatureUnit
from .config_manager import ConfigManager

class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def _get_system_idle_seconds() -> float:
    """Return user inactivity duration in seconds via Win32 GetLastInputInfo."""
    try:
        lii = _LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return max(0.0, millis / 1000.0)
    except Exception:
        pass
    return 0.0

class CoolerService(QObject):
    telemetry_updated = pyqtSignal(object, int, str, bool, bool, str) # (hw_data, displayed_val, unit, is_antiblink_active, connected, current_metric_name)

    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config
        self.sensor_engine = SensorEngine()
        self.protocol = CoolerProtocol()
        
        self.running = False
        self.thread = None
        self._playlist_idx = 0
        self._last_alt_switch_time = time.time()
        
        # Smooth stepping & animation states
        self._current_pump_val = 0.0
        self._target_pump_val = 0.0
        self._last_dispatched_val = -1
        self._startup_sweep_done = False
        self._last_heartbeat_time = 0.0

        # Phase 2 Context states
        self._game_load_counter = 0
        self._is_game_active = False
        self._last_power_on = True

    def start(self):
        if self.running:
            return
        self.running = True
        self.sensor_engine.start()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.sensor_engine.stop()
        self.protocol.disconnect()

    def reconnect_after_wake(self):
        """Re-initialize USB HID communication following a Windows system sleep/wake event."""
        try:
            print("[CoolerService] System resume detected - re-enumerating USB cooler...")
            self.protocol.disconnect()
            self._startup_sweep_done = False
            self._last_dispatched_val = -1
        except Exception as e:
            print(f"[CoolerService] Reconnect on wake error: {e}")

    def _play_startup_sweep(self, snap, temp_unit):
        """Play a smooth supercar gauge sweep sequence (00 -> 99 -> settle) on launch."""
        sweep_sequence = [0, 20, 45, 70, 90, 99, 99, 85, 70]
        for val in sweep_sequence:
            if not self.running or not self.protocol.connected:
                break
            packet = self.protocol.build_packet(snap, val, val, temp_unit)
            self.protocol.send_raw_packet(packet)
            self._current_pump_val = float(val)
            try:
                self.telemetry_updated.emit(snap, val, "°C", False, True, "System POST Sweep")
            except Exception:
                pass
            time.sleep(0.12)
        self._startup_sweep_done = True

    def _run_loop(self):
        snap = self.sensor_engine.get_snapshot()
        last_poll_time = 0.0

        while self.running:
            try:
                now = time.time()
                # 1. Ensure USB connection
                if not self.protocol.connected:
                    self.protocol.connect()
                    if self.protocol.connected:
                        self._startup_sweep_done = False

                # 2. Polling rate throttling from config (e.g. 500ms, 1000ms, 2000ms, 3000ms)
                poll_interval_sec = max(0.25, float(self.config.get("update_interval_ms", 1000)) / 1000.0)

                # Execute cycle when poll_interval_sec has elapsed
                if now - last_poll_time >= poll_interval_sec:
                    last_poll_time = now

                    # Refresh sensor snapshot
                    snap = self.sensor_engine.get_snapshot()

                    # 3. Read configuration parameters
                    display_power_on = self.config.get("display_power_on", True)
                    display_metric = self.config.get("display_metric", DisplayMetric.CPU_TEMP)
                    anti_blink_enabled = self.config.get("anti_blink_enabled", True)
                    anti_blink_mode = self.config.get("anti_blink_mode", AntiBlinkMode.CAP_84)
                    if not anti_blink_enabled:
                        anti_blink_mode = AntiBlinkMode.RAW
                        
                    temp_unit = self.config.get("temp_unit", TemperatureUnit.CELSIUS)
                    temp_offset = self.config.get("temp_offset", 0)
                    smooth_enabled = self.config.get("smooth_stepping", True)
                    anim_enabled = self.config.get("startup_animation", True)

                    # Handle Display Power OFF
                    if not display_power_on:
                        if self._last_power_on:
                            # User turned off display: stop sending HID packets so hardware standby turns LED off cleanly
                            self._current_pump_val = 0.0
                            self._last_dispatched_val = -1
                        self._last_power_on = False

                        try:
                            self.telemetry_updated.emit(
                                snap,
                                -1,
                                "",
                                False,
                                self.protocol.connected,
                                "DISPLAY OFF"
                            )
                        except RuntimeError:
                            break
                        time.sleep(0.5)
                        continue

                    # If transitioning back ON
                    if not self._last_power_on:
                        self._last_power_on = True
                        self._current_pump_val = 0.0

                    # Context configurations
                    auto_game_mode = self.config.get("auto_game_mode", False)
                    auto_game_thresh = self.config.get("auto_game_threshold_pct", 35)
                    desk_clock_enabled = self.config.get("desk_clock_enabled", False)
                    desk_clock_idle_sec = self.config.get("desk_clock_idle_sec", 300)
                    cycle_playlist = self.config.get("cycle_playlist", ["cpu_temp", "gpu_temp", "cpu_power", "cpu_load"])
                    cycle_interval = max(2, self.config.get("cycle_interval_sec", 5))

                    # 4. Context detection (Auto-Game & Desk Clock)
                    if snap.gpu_load >= auto_game_thresh:
                        self._game_load_counter = min(5, self._game_load_counter + 1)
                    else:
                        self._game_load_counter = max(0, self._game_load_counter - 1)
                    self._is_game_active = (self._game_load_counter >= 2)

                    idle_seconds = _get_system_idle_seconds()
                    is_idle_clock = desk_clock_enabled and (idle_seconds >= desk_clock_idle_sec)

                    # 5. Metric selection with Context Priority
                    metric_name = "CPU Temperature"
                    unit_label = "°C"
                    raw_primary_val = snap.cpu_temp
                    is_temperature = True

                    if is_idle_clock:
                        is_temperature = False
                        lt = time.localtime()
                        if int(now) % 6 < 3:
                            raw_primary_val = float(lt.tm_hour % 12 or 12)
                            metric_name = "Desk Clock (Hour)"
                        else:
                            raw_primary_val = float(lt.tm_min)
                            metric_name = "Desk Clock (Minute)"
                        unit_label = ""
                    elif auto_game_mode and self._is_game_active and display_metric != DisplayMetric.GPU_TEMP:
                        raw_primary_val = snap.gpu_temp
                        metric_name = "GPU Temperature (Game)"
                        unit_label = "°C" if temp_unit == TemperatureUnit.CELSIUS else "°F"
                        is_temperature = True
                    elif display_metric == DisplayMetric.ALTERNATING:
                        if not cycle_playlist:
                            cycle_playlist = ["cpu_temp", "gpu_temp"]
                        self._playlist_idx %= len(cycle_playlist)
                        if now - self._last_alt_switch_time >= cycle_interval:
                            self._playlist_idx = (self._playlist_idx + 1) % len(cycle_playlist)
                            self._last_alt_switch_time = now

                        cur_item = cycle_playlist[self._playlist_idx % len(cycle_playlist)]
                        if cur_item == "cpu_temp":
                            raw_primary_val = snap.cpu_temp
                            metric_name = "CPU Temperature"
                            unit_label = "°C" if temp_unit == TemperatureUnit.CELSIUS else "°F"
                            is_temperature = True
                        elif cur_item == "gpu_temp":
                            raw_primary_val = snap.gpu_temp
                            metric_name = "GPU Temperature"
                            unit_label = "°C" if temp_unit == TemperatureUnit.CELSIUS else "°F"
                            is_temperature = True
                        elif cur_item == "cpu_power":
                            raw_primary_val = min(99.0, max(0.0, float(snap.cpu_power)))
                            metric_name = "CPU Package Power"
                            unit_label = "W"
                            is_temperature = False
                        elif cur_item == "cpu_load":
                            raw_primary_val = snap.cpu_load
                            metric_name = "CPU Usage"
                            unit_label = "%"
                            is_temperature = False
                        elif cur_item == "gpu_load":
                            raw_primary_val = snap.gpu_load
                            metric_name = "GPU Usage"
                            unit_label = "%"
                            is_temperature = False
                        elif cur_item == "ram_load":
                            raw_primary_val = min(99.0, max(0.0, float(snap.ram_load)))
                            metric_name = "Memory Usage"
                            unit_label = "%"
                            is_temperature = False
                        else:
                            raw_primary_val = snap.cpu_temp
                            metric_name = "CPU Temperature"
                            unit_label = "°C" if temp_unit == TemperatureUnit.CELSIUS else "°F"
                            is_temperature = True
                    else:
                        if display_metric == DisplayMetric.CPU_TEMP:
                            raw_primary_val = snap.cpu_temp
                            metric_name = "CPU Temperature"
                            unit_label = "°C" if temp_unit == TemperatureUnit.CELSIUS else "°F"
                            is_temperature = True
                        elif display_metric == DisplayMetric.GPU_TEMP:
                            raw_primary_val = snap.gpu_temp
                            metric_name = "GPU Temperature"
                            unit_label = "°C" if temp_unit == TemperatureUnit.CELSIUS else "°F"
                            is_temperature = True
                        elif display_metric == DisplayMetric.CPU_LOAD:
                            raw_primary_val = snap.cpu_load
                            metric_name = "CPU Usage"
                            unit_label = "%"
                            is_temperature = False
                        elif display_metric == DisplayMetric.GPU_LOAD:
                            raw_primary_val = snap.gpu_load
                            metric_name = "GPU Usage"
                            unit_label = "%"
                            is_temperature = False
                        elif display_metric == DisplayMetric.CPU_POWER:
                            raw_primary_val = min(99.0, max(0.0, float(snap.cpu_power)))
                            metric_name = "CPU Package Power"
                            unit_label = "W"
                            is_temperature = False
                        elif display_metric == DisplayMetric.MAX_TEMP:
                            raw_primary_val = max(snap.cpu_temp, snap.gpu_temp)
                            metric_name = "Max Temp"
                            unit_label = "°C"
                            is_temperature = True
                        elif display_metric == DisplayMetric.AVG_TEMP:
                            raw_primary_val = (snap.cpu_temp + snap.gpu_temp) / 2.0
                            metric_name = "Avg Temp"
                            unit_label = "°C"
                            is_temperature = True

                    # 6. Process temperature & Anti-Blink capping
                    if is_temperature:
                        filtered_target = float(self.protocol.process_temperature(raw_primary_val, anti_blink_mode, temp_offset))
                        is_antiblink_active = anti_blink_enabled and (raw_primary_val >= 85.0) and (filtered_target < raw_primary_val)
                    else:
                        filtered_target = float(raw_primary_val)
                        is_antiblink_active = False

                    filtered_gpu = self.protocol.process_temperature(snap.gpu_temp, anti_blink_mode, 0)

                    # Execute startup sweep on initial connection
                    if self.protocol.connected and anim_enabled and not self._startup_sweep_done:
                        self._play_startup_sweep(snap, temp_unit)

                    # 7. Smooth Stepping & Deadband Hysteresis
                    if self._current_pump_val <= 0.0:
                        self._current_pump_val = filtered_target

                    if smooth_enabled:
                        delta = filtered_target - self._current_pump_val
                        if abs(delta) >= 0.6:
                            if delta > 0:
                                step = min(delta, max(1.0, delta * 0.70))
                                self._current_pump_val += step
                            else:
                                step = min(-delta, max(1.0, -delta * 0.50))
                                self._current_pump_val -= step
                    else:
                        self._current_pump_val = filtered_target

                    stepped_primary = int(round(self._current_pump_val))
                    stepped_primary = max(0, min(99, stepped_primary))

                    # 8. Send packet at exact user-configured rate
                    if self.protocol.connected:
                        packet = self.protocol.build_packet(snap, stepped_primary, filtered_gpu, temp_unit)
                        self.protocol.send_raw_packet(packet)
                        self._last_dispatched_val = stepped_primary
                        self._last_heartbeat_time = now

                    if not self.running:
                        break

                    display_val = stepped_primary
                    if temp_unit == TemperatureUnit.FAHRENHEIT and "Temp" in metric_name:
                        display_val = int(round(stepped_primary * 1.8 + 32))

                    try:
                        self.telemetry_updated.emit(
                            snap,
                            display_val,
                            unit_label,
                            is_antiblink_active,
                            self.protocol.connected,
                            metric_name
                        )
                    except RuntimeError:
                        break

            except Exception as e:
                if self.running:
                    print(f"[CoolerService] Error: {e}")

            time.sleep(0.08)
