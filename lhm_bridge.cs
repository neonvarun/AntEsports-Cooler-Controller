using System;
using System.Text;
using System.Threading;
using LibreHardwareMonitor.Hardware;

namespace AntEsportsSensorBridge
{
    class Program
    {
        static Computer computer;
        static UpdateVisitor visitor = new UpdateVisitor();

        static Computer CreateComputer()
        {
            return new Computer
            {
                IsCpuEnabled = true,
                IsGpuEnabled = true,
                IsMemoryEnabled = true,
                IsMotherboardEnabled = true,
                IsControllerEnabled = false,
                IsStorageEnabled = false
            };
        }

        static bool OpenComputer(out string error)
        {
            error = null;
            try
            {
                computer = CreateComputer();
                computer.Open();
                return true;
            }
            catch (Exception ex)
            {
                error = ex.Message;
                CloseComputer();
                return false;
            }
        }

        static void CloseComputer()
        {
            Computer current = computer;
            computer = null;
            if (current == null) return;

            try
            {
                current.Close();
            }
            catch
            {
                // The process is terminating or the next cycle will recreate the context.
                // Never leave cleanup exceptions on the JSON telemetry channel.
            }
        }

        static void WriteError(string message)
        {
            Console.WriteLine("{\"error\": " + EscapeJson(message) + "}");
        }

        public class UpdateVisitor : IVisitor
        {
            public void VisitComputer(IComputer computer)
            {
                computer.Traverse(this);
            }
            public void VisitHardware(IHardware hardware)
            {
                hardware.Update();
                foreach (IHardware subHardware in hardware.SubHardware)
                    subHardware.Accept(this);
            }
            public void VisitSensor(ISensor sensor) { }
            public void VisitParameter(IParameter parameter) { }
        }

        static void Main(string[] args)
        {
            Console.OutputEncoding = Encoding.UTF8;

            bool loop = args.Length > 0 && args[0] == "--loop";
            bool dump = args.Length > 0 && args[0] == "--dump";
            int interval = 1000;
            int parsedInterval;
            if (args.Length > 1 && int.TryParse(args[1], out parsedInterval))
            {
                interval = Math.Max(200, parsedInterval);
            }

            if (dump)
            {
                string openError;
                if (!OpenComputer(out openError))
                {
                    WriteError(openError);
                    return;
                }

                try
                {
                    computer.Accept(visitor);
                    DumpAllSensors(computer);
                }
                catch (Exception ex)
                {
                    WriteError(ex.Message);
                }
                finally
                {
                    CloseComputer();
                }
                return;
            }

            do
            {
                string openError;
                if (!OpenComputer(out openError))
                {
                    WriteError(openError);
                }
                else
                {
                    try
                    {
                        computer.Accept(visitor);
                        string json = CollectData();
                        Console.WriteLine(json);
                    }
                    catch (Exception ex)
                    {
                        WriteError(ex.Message);
                    }
                    finally
                    {
                        CloseComputer();
                    }
                }

                if (loop)
                {
                    Thread.Sleep(interval);
                }
            } while (loop);
        }

        static void ScanHardwareSensors(IHardware hw, ref float cpuTemp, ref int cpuTempPriority,
                                        ref float cpuLoad, ref float cpuClock, ref float cpuFan, ref float cpuPower,
                                         ref float gpuTemp, ref float gpuLoad, ref float gpuClock, ref float gpuFan, ref float gpuPower,
                                         ref float ramUsed, ref float ramTotal, ref float ramAvailable, ref float ramLoad, ref float mbCpuTemp,
                                         ref string cpuName, ref string gpuName)
        {
            // Board fan sensors are commonly exposed below the motherboard as a SuperIO child.
            // Inspect them at every level so the existing CPU fan field remains populated.
            foreach (ISensor sensor in hw.Sensors)
            {
                if (sensor.Value.HasValue && sensor.SensorType == SensorType.Fan && cpuFan <= 0)
                {
                    string fanName = sensor.Name;
                    if (fanName.IndexOf("CPU", StringComparison.OrdinalIgnoreCase) >= 0 ||
                        fanName.IndexOf("Fan #1", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        cpuFan = sensor.Value.Value;
                    }
                }
            }

            if (hw.HardwareType == HardwareType.Cpu)
            {
                if (string.IsNullOrEmpty(cpuName)) cpuName = hw.Name;
                foreach (ISensor sensor in hw.Sensors)
                {
                    if (!sensor.Value.HasValue) continue;
                    float val = sensor.Value.Value;

                    if (sensor.SensorType == SensorType.Temperature && val > 5 && val < 130)
                    {
                        string n = sensor.Name;
                        int priority = 1;
                        // AMD Zen 4 AM5 official temperature is Core (Tctl/Tdie)
                        if (n.IndexOf("Tctl", StringComparison.OrdinalIgnoreCase) >= 0)
                        {
                            priority = 4;
                        }
                        else if (n.IndexOf("Package", StringComparison.OrdinalIgnoreCase) >= 0 ||
                                 n.IndexOf("Core Max", StringComparison.OrdinalIgnoreCase) >= 0 ||
                                 n.IndexOf("CCD", StringComparison.OrdinalIgnoreCase) >= 0)
                        {
                            priority = 3;
                        }
                        else if (n.IndexOf("Tdie", StringComparison.OrdinalIgnoreCase) >= 0)
                        {
                            priority = 2;
                        }

                        if (priority > cpuTempPriority || (priority == cpuTempPriority && val > cpuTemp))
                        {
                            cpuTemp = val;
                            cpuTempPriority = priority;
                        }
                    }
                    else if (sensor.SensorType == SensorType.Load)
                    {
                        if (sensor.Name.IndexOf("Total", StringComparison.OrdinalIgnoreCase) >= 0)
                            cpuLoad = val;
                    }
                    else if (sensor.SensorType == SensorType.Clock)
                    {
                        if (sensor.Name.IndexOf("#1", StringComparison.OrdinalIgnoreCase) >= 0 || sensor.Name.IndexOf("Core", StringComparison.OrdinalIgnoreCase) >= 0)
                            cpuClock = Math.Max(cpuClock, val);
                    }
                    else if (sensor.SensorType == SensorType.Power)
                    {
                        if (sensor.Name.IndexOf("Package", StringComparison.OrdinalIgnoreCase) >= 0)
                            cpuPower = val;
                    }
                }
            }
            else if (hw.HardwareType == HardwareType.GpuNvidia || hw.HardwareType == HardwareType.GpuAmd || hw.HardwareType == HardwareType.GpuIntel)
            {
                if (string.IsNullOrEmpty(gpuName)) gpuName = hw.Name;
                foreach (ISensor sensor in hw.Sensors)
                {
                    if (!sensor.Value.HasValue) continue;
                    float val = sensor.Value.Value;

                    if (sensor.SensorType == SensorType.Temperature && val > 0 && val < 130)
                    {
                        if (sensor.Name.IndexOf("Core", StringComparison.OrdinalIgnoreCase) >= 0 || gpuTemp <= 0)
                            gpuTemp = val;
                    }
                    else if (sensor.SensorType == SensorType.Load && sensor.Name.IndexOf("Core", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        gpuLoad = val;
                    }
                    else if (sensor.SensorType == SensorType.Clock && sensor.Name.IndexOf("Core", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        gpuClock = val;
                    }
                    else if (sensor.SensorType == SensorType.Fan)
                    {
                        gpuFan = val;
                    }
                    else if (sensor.SensorType == SensorType.Power && (sensor.Name.IndexOf("Package", StringComparison.OrdinalIgnoreCase) >= 0 || sensor.Name.IndexOf("GPU", StringComparison.OrdinalIgnoreCase) >= 0))
                    {
                        gpuPower = val;
                    }
                }
            }
            else if (hw.HardwareType == HardwareType.Memory)
            {
                foreach (ISensor sensor in hw.Sensors)
                {
                    if (!sensor.Value.HasValue) continue;
                    float val = sensor.Value.Value;

                    if (sensor.SensorType == SensorType.Data && sensor.Name.IndexOf("Used", StringComparison.OrdinalIgnoreCase) >= 0)
                        ramUsed = val * 1024.0f;
                    else if (sensor.SensorType == SensorType.Data && sensor.Name.IndexOf("Total", StringComparison.OrdinalIgnoreCase) >= 0)
                        ramTotal = val * 1024.0f;
                    else if (sensor.SensorType == SensorType.Data &&
                             sensor.Name.IndexOf("Available", StringComparison.OrdinalIgnoreCase) >= 0 &&
                             hw.Name.IndexOf("Total", StringComparison.OrdinalIgnoreCase) >= 0)
                        ramAvailable = val * 1024.0f;
                    else if (sensor.SensorType == SensorType.Load && sensor.Name.IndexOf("Memory", StringComparison.OrdinalIgnoreCase) >= 0)
                        ramLoad = val;
                }
            }
            else if (hw.HardwareType == HardwareType.Motherboard)
            {
                foreach (ISensor sensor in hw.Sensors)
                {
                    if (!sensor.Value.HasValue) continue;
                    float val = sensor.Value.Value;

                    if (sensor.SensorType == SensorType.Fan && (sensor.Name.IndexOf("CPU", StringComparison.OrdinalIgnoreCase) >= 0 || sensor.Name.IndexOf("Fan #1", StringComparison.OrdinalIgnoreCase) >= 0))
                    {
                        if (cpuFan <= 0) cpuFan = val;
                    }
                    else if (sensor.SensorType == SensorType.Temperature && val > 15 && val < 115)
                    {
                        if (sensor.Name.IndexOf("CPU", StringComparison.OrdinalIgnoreCase) >= 0)
                            mbCpuTemp = val;
                    }
                }
            }

            // Recurse into SubHardware
            foreach (IHardware sub in hw.SubHardware)
            {
                ScanHardwareSensors(sub, ref cpuTemp, ref cpuTempPriority,
                                    ref cpuLoad, ref cpuClock, ref cpuFan, ref cpuPower,
                                     ref gpuTemp, ref gpuLoad, ref gpuClock, ref gpuFan, ref gpuPower,
                                     ref ramUsed, ref ramTotal, ref ramAvailable, ref ramLoad, ref mbCpuTemp,
                                     ref cpuName, ref gpuName);
            }
        }

        static string CollectData()
        {
            float cpuTemp = 0;
            int cpuTempPriority = 0;
            float cpuLoad = 0;
            float cpuClock = 0;
            float cpuFan = 0;
            float cpuPower = 0;

            float gpuTemp = 0;
            float gpuLoad = 0;
            float gpuClock = 0;
            float gpuFan = 0;
            float gpuPower = 0;

            float ramUsed = 0;
            float ramTotal = 0;
            float ramAvailable = 0;
            float ramLoad = 0;
            float mbCpuTemp = 0;
            string cpuName = "";
            string gpuName = "";

            foreach (IHardware hardware in computer.Hardware)
            {
                ScanHardwareSensors(hardware, ref cpuTemp, ref cpuTempPriority,
                                    ref cpuLoad, ref cpuClock, ref cpuFan, ref cpuPower,
                                    ref gpuTemp, ref gpuLoad, ref gpuClock, ref gpuFan, ref gpuPower,
                                    ref ramUsed, ref ramTotal, ref ramAvailable, ref ramLoad, ref mbCpuTemp,
                                    ref cpuName, ref gpuName);
            }

            // LHM exposes physical memory as Used + Available on some systems.
            if (ramTotal <= 0 && ramUsed > 0 && ramAvailable > 0)
                ramTotal = ramUsed + ramAvailable;

            // If CPU temp wasn't found from direct CPU sensors, fallback to motherboard CPU temp sensor
            if (cpuTemp <= 0 && mbCpuTemp > 0)
            {
                cpuTemp = mbCpuTemp;
            }

            if (float.IsNaN(cpuTemp) || float.IsInfinity(cpuTemp)) cpuTemp = 0;
            if (float.IsNaN(cpuLoad) || float.IsInfinity(cpuLoad)) cpuLoad = 0;
            if (float.IsNaN(cpuClock) || float.IsInfinity(cpuClock)) cpuClock = 0;
            if (float.IsNaN(cpuFan) || float.IsInfinity(cpuFan)) cpuFan = 0;
            if (float.IsNaN(cpuPower) || float.IsInfinity(cpuPower)) cpuPower = 0;

            if (float.IsNaN(gpuTemp) || float.IsInfinity(gpuTemp)) gpuTemp = 0;
            if (float.IsNaN(gpuLoad) || float.IsInfinity(gpuLoad)) gpuLoad = 0;
            if (float.IsNaN(gpuClock) || float.IsInfinity(gpuClock)) gpuClock = 0;
            if (float.IsNaN(gpuFan) || float.IsInfinity(gpuFan)) gpuFan = 0;
            if (float.IsNaN(gpuPower) || float.IsInfinity(gpuPower)) gpuPower = 0;

            if (float.IsNaN(ramUsed) || float.IsInfinity(ramUsed)) ramUsed = 0;
            if (float.IsNaN(ramTotal) || float.IsInfinity(ramTotal)) ramTotal = 0;
            if (float.IsNaN(ramLoad) || float.IsInfinity(ramLoad)) ramLoad = 0;

            if (string.IsNullOrEmpty(cpuName)) cpuName = "AMD Ryzen 9 7900X";
            if (string.IsNullOrEmpty(gpuName)) gpuName = "AMD Radeon(TM) Graphics";

            return string.Format(System.Globalization.CultureInfo.InvariantCulture,
                "{{\"cpu_temp\":{0:0.0},\"cpu_load\":{1:0.0},\"cpu_clock\":{2:0},\"cpu_fan\":{3:0},\"cpu_power\":{4:0.0}," +
                "\"gpu_temp\":{5:0.0},\"gpu_load\":{6:0.0},\"gpu_clock\":{7:0},\"gpu_fan\":{8:0},\"gpu_power\":{9:0.0}," +
                "\"ram_used_mb\":{10:0},\"ram_total_mb\":{11:0},\"ram_load\":{12:0.0}," +
                "\"cpu_name\":{13},\"gpu_name\":{14},\"backend\":\"LibreHardwareMonitor/PawnIO\"}}",
                cpuTemp, cpuLoad, cpuClock, cpuFan, cpuPower,
                gpuTemp, gpuLoad, gpuClock, gpuFan, gpuPower,
                ramUsed, ramTotal, ramLoad,
                EscapeJson(cpuName), EscapeJson(gpuName));
        }

        static string EscapeJson(string s)
        {
            if (s == null) return "\"\"";
            return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "").Replace("\n", "\\n") + "\"";
        }

        static void DumpAllSensors(IComputer comp)
        {
            foreach (IHardware hw in comp.Hardware)
            {
                DumpHardware(hw, "");
            }
        }

        static void DumpHardware(IHardware hw, string indent)
        {
            Console.WriteLine(string.Format("{0}[{1}] {2}", indent, hw.HardwareType, hw.Name));
            foreach (ISensor s in hw.Sensors)
            {
                Console.WriteLine(string.Format("{0}  -> ({1}) {2} = {3}", indent, s.SensorType, s.Name, s.Value));
            }
            foreach (IHardware sub in hw.SubHardware)
            {
                DumpHardware(sub, indent + "  ");
            }
        }
    }
}
