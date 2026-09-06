import os
import sys
import win32com.client

def create_shortcuts():
    shell = win32com.client.Dispatch("WScript.Shell")
    
    desktop = shell.SpecialFolders("Desktop")
    programs = shell.SpecialFolders("Programs")
    
    proj_dir = os.path.abspath(os.path.dirname(__file__))
    exe_path = os.path.join(proj_dir, "AntEsports.exe")
    
    # Clean up any legacy or duplicate shortcuts on Desktop
    old_shortcuts = [
        os.path.join(desktop, "Ant Esports Cooler.lnk"),
        os.path.join(desktop, "AntEsports.lnk"),
        os.path.join(desktop, "Ant Esports.lnk"),
        os.path.join(programs, "Ant Esports Cooler.lnk")
    ]
    for old_sc in old_shortcuts:
        if os.path.exists(old_sc):
            try:
                os.remove(old_sc)
                print(f"[REMOVED] Legacy shortcut: {old_sc}")
            except Exception as e:
                print(f"[WARN] Could not remove {old_sc}: {e}")

    # Primary shortcuts
    shortcuts = [
        os.path.join(desktop, "Ant Esports ICEStorm-240.lnk"),
        os.path.join(programs, "Ant Esports ICEStorm-240.lnk")
    ]
    
    pythonw_path = r"C:\Users\USER\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe"
    if not os.path.exists(pythonw_path):
        pythonw_path = sys.executable.replace("python.exe", "pythonw.exe")
    
    main_py = os.path.join(proj_dir, "main.py")
    icon_path = os.path.join(proj_dir, "assets", "app_icon.ico")
    
    for sc_path in shortcuts:
        sc = shell.CreateShortcut(sc_path)
        sc.TargetPath = pythonw_path
        sc.Arguments = f'"{main_py}"'
        sc.WorkingDirectory = proj_dir
        sc.IconLocation = f"{icon_path},0"
        sc.Description = "Ant Esports ICEStorm-240 Dashboard & Hardware Telemetry"
        sc.Save()
        
        # Set SLDF_RUNAS_USER (byte 0x15 bit 5, 0x20) so Windows prompts for UAC permission on click
        try:
            with open(sc_path, "rb") as f:
                data = bytearray(f.read())
            data[0x15] |= 0x20
            with open(sc_path, "wb") as f:
                f.write(data)
            print(f"[OK] Created admin-elevated shortcut: {sc_path}")
        except Exception as e:
            print(f"[WARN] Could not set admin flag on {sc_path}: {e}")

if __name__ == "__main__":
    create_shortcuts()

