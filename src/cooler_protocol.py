import hid
import time
import math

class AntiBlinkMode:
    CAP_84 = "cap_84"       # Clamps displayed temp at 84°C to prevent hardware blinking
    COMPRESS = "compress"   # Smoothly scales 75°C-100°C down into 75°C-84°C
    RAW = "raw"             # No filtering (allows default hardware blinking at >=85°C)

class DisplayMetric:
    CPU_TEMP = "cpu_temp"
    GPU_TEMP = "gpu_temp"
    CPU_LOAD = "cpu_load"
    GPU_LOAD = "gpu_load"
    CPU_POWER = "cpu_power"
    ALTERNATING = "alternating"
    MAX_TEMP = "max_temp"
    AVG_TEMP = "avg_temp"

class TemperatureUnit:
    CELSIUS = "C"
    FAHRENHEIT = "F"

class CoolerProtocol:
    VID = 0x5131
    PID = 0x2007
    
    def __init__(self):
        self.device = None
        self.connected = False
        self.device_path = None
        self.last_error = None
        
    def find_devices(self):
        """Enumerate connected Ant Esports cooler devices."""
        try:
            return hid.enumerate(self.VID, self.PID)
        except Exception as e:
            self.last_error = str(e)
            return []

    def connect(self):
        """Connect to the first available cooler."""
        try:
            devices = self.find_devices()
            if not devices:
                self.connected = False
                self.last_error = "Device VID 0x5131 / PID 0x2007 not found."
                return False
                
            self.device_path = devices[0]['path']
            self.device = hid.device()
            self.device.open_path(self.device_path)
            self.device.set_nonblocking(1)
            self.connected = True
            self.last_error = None
            return True
        except Exception as e:
            self.connected = False
            self.last_error = str(e)
            if self.device:
                try:
                    self.device.close()
                except Exception:
                    pass
                self.device = None
            return False

    def disconnect(self):
        self.connected = False
        if self.device:
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None

    def process_temperature(self, temp_c, anti_blink_mode=AntiBlinkMode.CAP_84, temp_offset=0):
        """
        Apply offset and anti-blink filtering to a Celsius temperature.
        Returns the filtered Celsius integer value (0-100).
        """
        temp = float(temp_c) + float(temp_offset)
        temp = max(0.0, min(110.0, temp))
        
        if anti_blink_mode == AntiBlinkMode.CAP_84:
            # If >= 85°C, cap at 84°C to prevent the MCU from flashing
            if temp >= 85.0:
                temp = 84.0
        elif anti_blink_mode == AntiBlinkMode.COMPRESS:
            # Linearly compress 75°C - 100°C into 75°C - 84°C
            if temp > 75.0:
                # 75 + (temp - 75) * (9 / 25)
                temp = 75.0 + (temp - 75.0) * 0.36
                temp = min(84.0, temp)
        elif anti_blink_mode == AntiBlinkMode.RAW:
            pass
            
        return int(round(temp))

    def build_packet(self, hw_data, primary_temp_c, gpu_temp_c, unit=TemperatureUnit.CELSIUS):
        """
        Build the 65-byte HID report payload.
        Byte 0: Report ID (0x00)
        Byte 1: Opcode (0x40)
        Byte 2: Primary Display Temp (CPU or mapped metric)
        Byte 3: CPU Usage %
        Byte 4-5: CPU MHz
        Byte 6-7: CPU Fan RPM
        Byte 8-9: CPU Power Watts
        Byte 10: GPU Temp
        Byte 11: GPU Usage %
        Byte 12-13: GPU MHz
        Byte 14-15: GPU Fan RPM
        Byte 16-17: GPU Power Watts
        Byte 18: RAM Usage %
        Byte 19-20: RAM Used MB
        Byte 21: Disk Usage %
        Byte 22-23: Disk Total GB
        Byte 24-64: Zeroes
        """
        packet = [0] * 65
        packet[0] = 0x00
        packet[1] = 0x40
        
        # Primary / CPU Temperature byte
        t_cpu = max(0, min(100, int(primary_temp_c)))
        if unit == TemperatureUnit.FAHRENHEIT:
            # Set bit 7 (0x80) for Fahrenheit mode
            packet[2] = (t_cpu & 0x7F) | 0x80
        else:
            packet[2] = t_cpu & 0x7F
            
        # CPU Load
        packet[3] = max(0, min(100, int(hw_data.cpu_load)))
        
        # CPU Clock MHz (16-bit Big Endian)
        cpu_clk = max(0, min(65535, int(hw_data.cpu_clock)))
        packet[4] = (cpu_clk >> 8) & 0xFF
        packet[5] = cpu_clk & 0xFF
        
        # CPU Fan RPM
        cpu_fan = max(0, min(65535, int(hw_data.cpu_fan)))
        packet[6] = (cpu_fan >> 8) & 0xFF
        packet[7] = cpu_fan & 0xFF
        
        # CPU Power Watts
        cpu_pwr = max(0, min(65535, int(hw_data.cpu_power)))
        packet[8] = (cpu_pwr >> 8) & 0xFF
        packet[9] = cpu_pwr & 0xFF
        
        # GPU Temperature byte
        t_gpu = max(0, min(100, int(gpu_temp_c)))
        if unit == TemperatureUnit.FAHRENHEIT:
            packet[10] = (t_gpu & 0x7F) | 0x80
        else:
            packet[10] = t_gpu & 0x7F
            
        # GPU Load
        packet[11] = max(0, min(100, int(hw_data.gpu_load)))
        
        # GPU Clock MHz
        gpu_clk = max(0, min(65535, int(hw_data.gpu_clock)))
        packet[12] = (gpu_clk >> 8) & 0xFF
        packet[13] = gpu_clk & 0xFF
        
        # GPU Fan RPM
        gpu_fan = max(0, min(65535, int(hw_data.gpu_fan)))
        packet[14] = (gpu_fan >> 8) & 0xFF
        packet[15] = gpu_fan & 0xFF
        
        # GPU Power Watts
        gpu_pwr = max(0, min(65535, int(hw_data.gpu_power)))
        packet[16] = (gpu_pwr >> 8) & 0xFF
        packet[17] = gpu_pwr & 0xFF
        
        # RAM Load %
        packet[18] = max(0, min(100, int(hw_data.ram_load)))
        
        # RAM Used MB
        ram_used = max(0, min(65535, int(hw_data.ram_used_mb)))
        packet[19] = (ram_used >> 8) & 0xFF
        packet[20] = ram_used & 0xFF
        
        # Disk Load %
        packet[21] = max(0, min(100, int(hw_data.disk_load)))
        
        # Disk Total GB
        disk_tot = max(0, min(65535, int(hw_data.disk_total_gb)))
        packet[22] = (disk_tot >> 8) & 0xFF
        packet[23] = disk_tot & 0xFF
        
        return packet

    def build_blank_packet(self):
        """
        Build a 65-byte zeroed packet with Opcode 0x40 to blank all digital segments.
        """
        packet = [0] * 65
        packet[0] = 0x00
        packet[1] = 0x40
        return packet

    def send_raw_packet(self, packet_bytes):
        """Send a 65-byte packet directly to the device."""
        if not self.connected or not self.device:
            if not self.connect():
                return False
        try:
            res = self.device.write(packet_bytes)
            if res is None or res < 0:
                self.disconnect()
                return False
            return res == len(packet_bytes)
        except Exception as e:
            self.last_error = str(e)
            self.disconnect()
            return False
