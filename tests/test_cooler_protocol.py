import unittest

from src.cooler_protocol import AntiBlinkMode, CoolerProtocol, TemperatureUnit
from src.sensor_engine import HardwareData


class CoolerProtocolTests(unittest.TestCase):
    def test_packet_shape_and_existing_telemetry_offsets(self):
        protocol = CoolerProtocol()
        data = HardwareData()
        data.cpu_load = 42.0
        data.cpu_clock = 5200
        data.cpu_fan = 1600
        data.cpu_power = 80.0
        data.gpu_temp = 55.0
        data.gpu_load = 33.0
        data.gpu_clock = 2400
        data.gpu_fan = 1200
        data.gpu_power = 150.0
        data.ram_load = 70.0
        data.ram_used_mb = 12000
        data.disk_load = 12.0
        data.disk_total_gb = 1000

        packet = protocol.build_packet(data, 72.0, 55.0, TemperatureUnit.CELSIUS)

        self.assertEqual(len(packet), 65)
        self.assertEqual(packet[0], 0)
        self.assertEqual(packet[1], 0x40)
        self.assertEqual(packet[2], 72)
        self.assertEqual(packet[3], 42)
        self.assertEqual(packet[10], 55)
        self.assertEqual(packet[11], 33)

    def test_cap_mode_keeps_firmware_safe_temperature_limit(self):
        protocol = CoolerProtocol()
        self.assertEqual(
            protocol.process_temperature(99.0, AntiBlinkMode.CAP_84),
            84,
        )


if __name__ == "__main__":
    unittest.main()
