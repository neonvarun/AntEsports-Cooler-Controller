import os
import sys
import time
import ctypes
import traceback
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from src.config_manager import ConfigManager
from src.cooler_service import CoolerService
from src.ui.main_window import MainWindow

SINGLE_INSTANCE_SERVER = "AntEsports_ICEStorm240_IPC"

def is_admin_user():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False

def setup_exception_logging():
    def excepthook(exc_type, exc_value, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print("[CRITICAL] Unhandled Exception:\n", msg)
        try:
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash.log")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- Exception at {time.ctime()} ---\n{msg}")
        except Exception:
            pass
        try:
            ctypes.windll.user32.MessageBoxW(0, f"Ant Esports Control Center Error:\n\n{msg[:400]}", "Ant Esports ICEStorm-240", 0x10)
        except Exception:
            pass
    sys.excepthook = excepthook

setup_exception_logging()

def main():
    # 1. Single-Instance Check via Local Socket IPC
    # If another instance is running, signal it to restore its window and exit immediately
    probe_app = None
    if not QApplication.instance():
        probe_app = QApplication(sys.argv)
        
    probe_socket = QLocalSocket()
    probe_socket.connectToServer(SINGLE_INSTANCE_SERVER)
    if probe_socket.waitForConnected(300):
        probe_socket.write(b"SHOW\n")
        probe_socket.waitForBytesWritten(1000)
        probe_socket.disconnectFromServer()
        sys.exit(0)

    # 2. Elevation Request if not admin
    if not is_admin_user() and "--no-elevate" not in sys.argv:
        try:
            main_py = os.path.abspath(sys.argv[0])
            clean_args = [arg for arg in sys.argv[1:] if arg != "--admin"]
            params = f'"{main_py}" ' + " ".join(clean_args)
            ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params.strip(), None, 1)
            if ret > 32:
                sys.exit(0)
        except Exception:
            pass

    # 3. Suppress Legacy scheduled task and old binaries if running as admin
    if is_admin_user():
        try:
            import subprocess
            CREATE_NO_WINDOW = 0x08000000
            subprocess.run('schtasks /change /tn "ANTESPORTSStartupTaskOKver---ABCDEF6543A7" /disable', shell=True, creationflags=CREATE_NO_WINDOW)
            subprocess.run('sc start R0ANTESPORTS', shell=True, creationflags=CREATE_NO_WINDOW)
            subprocess.run('taskkill /f /im ANTESPORTS.exe', shell=True, creationflags=CREATE_NO_WINDOW)
            subprocess.run('taskkill /f /im allComputerInfoGetPro.exe', shell=True, creationflags=CREATE_NO_WINDOW)
        except Exception:
            pass

    # 4. AppUserModelID for proper Windows taskbar grouping
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AntEsports.ICEStorm240.Dashboard.1.0")
        except Exception:
            pass

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Load high-resolution official icon
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "app_icon.ico")
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)
    else:
        app_icon = QIcon()

    config = ConfigManager()
    service = CoolerService(config)
    service.start()
    window = MainWindow(config, service)
    if not app_icon.isNull():
        window.setWindowIcon(app_icon)

    # Setup IPC Server for single instance activation
    QLocalServer.removeServer(SINGLE_INSTANCE_SERVER)
    ipc_server = QLocalServer()
    ipc_server.listen(SINGLE_INSTANCE_SERVER)

    def handle_ipc():
        client = ipc_server.nextPendingConnection()
        if client:
            client.readyRead.connect(lambda: on_ipc_read(client))

    def on_ipc_read(client):
        try:
            data = client.readAll().data().decode("utf-8", errors="ignore").strip()
            if "SHOW" in data:
                window.showNormal()
                window.raise_()
                window.activateWindow()
        except Exception:
            pass
        finally:
            client.disconnectFromServer()

    ipc_server.newConnection.connect(handle_ipc)

    def on_about_to_quit():
        try:
            ipc_server.close()
            QLocalServer.removeServer(SINGLE_INSTANCE_SERVER)
        except Exception:
            pass
        service.stop()

    app.aboutToQuit.connect(on_about_to_quit)

    start_min = "--minimized" in sys.argv or config.get("start_minimized", False)
    if not start_min:
        window.show()
        window.raise_()
        window.activateWindow()
    else:
        window.hide()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
