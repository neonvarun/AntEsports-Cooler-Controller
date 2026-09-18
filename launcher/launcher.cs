using System;
using System.Diagnostics;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Windows.Forms;

namespace AntEsportsLauncher
{
    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            string appDir = AppDomain.CurrentDomain.BaseDirectory;

            // 1. Single-instance IPC check:
            // Connect to Qt QLocalServer pipe "AntEsports_ICEStorm240_IPC"
            try
            {
                using (var pipe = new NamedPipeClientStream(".", "AntEsports_ICEStorm240_IPC", PipeDirection.InOut))
                {
                    pipe.Connect(350);
                    byte[] msg = Encoding.UTF8.GetBytes("SHOW\n");
                    pipe.Write(msg, 0, msg.Length);
                    pipe.Flush();
                    return; // Previous instance signaled and raised; exit cleanly
                }
            }
            catch { }

            // 2. Suppress conflicting legacy scheduled task
            try
            {
                var schProc = new Process
                {
                    StartInfo = new ProcessStartInfo
                    {
                        FileName = "schtasks.exe",
                        Arguments = "/change /tn \"ANTESPORTSStartupTaskOKver---ABCDEF6543A7\" /disable",
                        CreateNoWindow = true,
                        UseShellExecute = false
                    }
                };
                schProc.Start();
                schProc.WaitForExit(1000);
            }
            catch { }

            // 3. Terminate any legacy ANTESPORTS.exe if running so our Control Center gets exclusive USB HID ownership
            try
            {
                foreach (var p in Process.GetProcessesByName("ANTESPORTS"))
                {
                    try { p.Kill(); } catch { }
                }
                foreach (var p in Process.GetProcessesByName("allComputerInfoGetPro"))
                {
                    try { p.Kill(); } catch { }
                }
            }
            catch { }

            // 4. Locate pythonw.exe
            string pythonw = FindPythonw(appDir);
            string mainPy = Path.Combine(appDir, "main.py");

            var startInfo = new ProcessStartInfo
            {
                FileName = pythonw,
                Arguments = "\"" + mainPy + "\" " + string.Join(" ", args),
                WorkingDirectory = appDir,
                UseShellExecute = false,
                CreateNoWindow = true
            };

            try
            {
                Process.Start(startInfo);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Unable to start Ant Esports Control Center:\n" + ex.Message,
                                "Ant Esports ICEStorm-240",
                                MessageBoxButtons.OK,
                                MessageBoxIcon.Error);
            }
        }

        static string FindPythonw(string appDir)
        {
            try
            {
                string configPath = Path.Combine(appDir, "python_path.txt");
                if (File.Exists(configPath))
                {
                    string p = File.ReadAllText(configPath).Trim();
                    if (File.Exists(p)) return p;
                }

                string userProfile = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
                string[] candidates = new string[]
                {
                    Path.Combine(appDir, @".venv\Scripts\pythonw.exe"),
                    Path.Combine(userProfile, @"AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"),
                    Path.Combine(userProfile, @"AppData\Local\Programs\Python\Python312\pythonw.exe"),
                    Path.Combine(userProfile, @"AppData\Local\Programs\Python\Python311\pythonw.exe"),
                    Path.Combine(userProfile, @"AppData\Local\Programs\Python\Python313\pythonw.exe"),
                    Path.Combine(userProfile, @"AppData\Local\Python\bin\pythonw.exe"),
                    @"C:\Python312\pythonw.exe",
                    @"C:\Python311\pythonw.exe"
                };

                foreach (var c in candidates)
                {
                    if (File.Exists(c)) return c;
                }
            }
            catch { }

            return "pythonw.exe";
        }
    }
}
