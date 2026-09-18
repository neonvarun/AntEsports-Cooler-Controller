import io
import tempfile
import unittest

from src.sensor_engine import PawnIOStatus, SensorEngine


class _FakePawnIO:
    def __init__(self, status=PawnIOStatus.READY):
        self.status = status
        self.last_detail = ""

    def ensure_ready(self):
        return self.status


class _FakeProcess:
    def __init__(self, text):
        self.stdout = io.StringIO(text)


class SensorEngineTests(unittest.TestCase):
    def make_engine(self, status=PawnIOStatus.READY):
        engine = SensorEngine(
            bridge_path=tempfile.gettempdir() + "\\missing-lhm-bridge.exe",
            pawnio_manager=_FakePawnIO(status),
        )
        engine.pawnio_status = status
        return engine

    def test_hardware_backend_reader_accepts_valid_json_after_noise(self):
        engine = self.make_engine()
        engine.running = True
        engine.bridge_process = _FakeProcess(
            "diagnostic text\n"
            "{not-json}\n"
            '{"cpu_temp": 72.5, "backend": "LibreHardwareMonitor/PawnIO"}\n'
        )

        engine._read_bridge_output()

        self.assertEqual(engine._last_lhm_data["cpu_temp"], 72.5)
        self.assertEqual(engine._last_lhm_data["backend"], "LibreHardwareMonitor/PawnIO")

    def test_missing_backend_status_is_actionable(self):
        engine = self.make_engine(PawnIOStatus.REBOOT_REQUIRED)
        self.assertEqual(engine._status_text(0.0), "Restart required for PawnIO")

    def test_installed_backend_without_elevation_is_actionable(self):
        engine = self.make_engine(PawnIOStatus.READY)
        engine.is_admin = False
        self.assertEqual(engine._status_text(0.0), "PawnIO requires Administrator")

    def test_hardware_data_starts_without_synthetic_temperature(self):
        engine = self.make_engine(PawnIOStatus.MISSING)
        snapshot = engine.get_snapshot()
        self.assertEqual(snapshot.cpu_temp, 0.0)
        self.assertFalse(snapshot.is_sensor_real)
        self.assertEqual(snapshot.sensor_backend_status, PawnIOStatus.MISSING.value)


if __name__ == "__main__":
    unittest.main()
