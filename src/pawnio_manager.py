"""Secure, offline management of the signed PawnIO prerequisite."""

from __future__ import annotations

import ctypes
import hashlib
import os
import re
import subprocess
import time
import winreg
from ctypes import wintypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class PawnIOStatus(str, Enum):
    READY = "READY"
    MISSING = "MISSING"
    OUTDATED = "OUTDATED"
    NOT_ELEVATED = "NOT_ELEVATED"
    INVALID_PACKAGE = "INVALID_PACKAGE"
    INSTALL_FAILED = "INSTALL_FAILED"
    REBOOT_REQUIRED = "REBOOT_REQUIRED"
    LEGACY_BLOCKED = "LEGACY_BLOCKED"
    LEGACY_CLEANUP_FAILED = "LEGACY_CLEANUP_FAILED"


@dataclass(frozen=True)
class PawnIOInstallation:
    version: str | None
    service_present: bool
    driver_path: str | None = None
    driver_signed: bool | None = None


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _WINTRUST_FILE_INFO(ctypes.Structure):
    _fields_ = [
        ("cbStruct", wintypes.DWORD),
        ("pcwszFilePath", wintypes.LPCWSTR),
        ("hFile", wintypes.HANDLE),
        ("pgKnownSubject", ctypes.POINTER(_GUID)),
    ]


class _WINTRUST_DATA(ctypes.Structure):
    _fields_ = [
        ("cbStruct", wintypes.DWORD),
        ("pPolicyCallbackData", wintypes.LPVOID),
        ("pSIPClientData", wintypes.LPVOID),
        ("dwUIChoice", wintypes.DWORD),
        ("fdwRevocationChecks", wintypes.DWORD),
        ("dwUnionChoice", wintypes.DWORD),
        ("pFile", wintypes.LPVOID),
        ("dwStateAction", wintypes.DWORD),
        ("hWVTStateData", wintypes.HANDLE),
        ("pwszURLReference", wintypes.LPCWSTR),
        ("dwProvFlags", wintypes.DWORD),
        ("dwUIContext", wintypes.DWORD),
    ]


class PawnIOManager:
    """Install and validate PawnIO without downloading or weakening Windows security."""

    MINIMUM_VERSION = (2, 2, 0)
    INSTALLER_SHA256 = "1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032"
    LEGACY_DRIVER_SHA256 = "11bd2c9f9e2397c9a16e0990e4ed2cf0679498fe0fd418a3dfdac60b5c160ee5"
    UNINSTALL_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO"
    SERVICE_KEY = r"SYSTEM\CurrentControlSet\Services\PawnIO"

    def __init__(self, app_dir: str | os.PathLike[str] | None = None):
        self.app_dir = Path(app_dir or Path(__file__).resolve().parent.parent)
        self.installer_path = self.app_dir / "bin" / "PawnIO_setup.exe"
        self.last_detail = ""

    @staticmethod
    def _is_admin() -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    @staticmethod
    def _version_tuple(version: str | None) -> tuple[int, ...]:
        if not version:
            return ()
        return tuple(int(part) for part in re.findall(r"\d+", str(version))[:4])

    @classmethod
    def _open_machine_key(cls, subkey: str):
        access = winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
        try:
            return winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey, 0, access)
        except OSError:
            return None

    @classmethod
    def _read_machine_value(cls, subkey: str, value_name: str) -> str | None:
        key = cls._open_machine_key(subkey)
        if key is None:
            return None
        try:
            value, _ = winreg.QueryValueEx(key, value_name)
            return str(value)
        except OSError:
            return None
        finally:
            winreg.CloseKey(key)

    @classmethod
    def installed_info(cls) -> PawnIOInstallation:
        version = cls._read_machine_value(cls.UNINSTALL_KEY, "DisplayVersion")
        service_key = cls._open_machine_key(cls.SERVICE_KEY)
        service_present = service_key is not None
        driver_path = None
        driver_signed = None
        if service_key is not None:
            try:
                image_path, _ = winreg.QueryValueEx(service_key, "ImagePath")
                resolved_path = cls._extract_image_path(image_path)
                if resolved_path is not None:
                    driver_path = str(resolved_path)
                    driver_signed = resolved_path.is_file() and cls._verify_authenticode(resolved_path)
                else:
                    driver_signed = False
            except OSError:
                driver_signed = False
            finally:
                winreg.CloseKey(service_key)
        return PawnIOInstallation(
            version=version,
            service_present=service_present,
            driver_path=driver_path,
            driver_signed=driver_signed,
        )

    @classmethod
    def is_ready(cls) -> bool:
        installed = cls.installed_info()
        return (
            installed.service_present
            and cls._version_tuple(installed.version) >= cls.MINIMUM_VERSION
            and installed.driver_signed is not False
        )

    @staticmethod
    def _verify_authenticode(path: Path) -> bool:
        """Verify a PE signature through WinVerifyTrust without invoking a shell."""
        try:
            wintrust = ctypes.windll.wintrust
            wintrust.WinVerifyTrust.argtypes = [
                wintypes.HWND,
                ctypes.POINTER(_GUID),
                ctypes.POINTER(_WINTRUST_DATA),
            ]
            wintrust.WinVerifyTrust.restype = wintypes.LONG

            action = _GUID(
                0x00AAC56B,
                0xCD44,
                0x11D0,
                (ctypes.c_ubyte * 8)(0x8C, 0xC2, 0x00, 0xC0, 0x4F, 0xC2, 0x95, 0xEE),
            )
            file_info = _WINTRUST_FILE_INFO(
                ctypes.sizeof(_WINTRUST_FILE_INFO),
                str(path),
                None,
                None,
            )
            trust_data = _WINTRUST_DATA(
                ctypes.sizeof(_WINTRUST_DATA),
                None,
                None,
                2,  # WTD_UI_NONE
                0,  # WTD_REVOKE_NONE
                1,  # WTD_CHOICE_FILE
                ctypes.cast(ctypes.pointer(file_info), wintypes.LPVOID),
                1,  # WTD_STATEACTION_VERIFY
                None,
                None,
                0,
                0,
            )

            result = wintrust.WinVerifyTrust(None, ctypes.byref(action), ctypes.byref(trust_data))
            trust_data.dwStateAction = 2  # WTD_STATEACTION_CLOSE
            wintrust.WinVerifyTrust(None, ctypes.byref(action), ctypes.byref(trust_data))
            return result == 0
        except Exception:
            return False

    def verify_installer(self) -> bool:
        if not self.installer_path.is_file():
            self.last_detail = f"Missing bundled installer: {self.installer_path}"
            return False

        try:
            digest = hashlib.sha256(self.installer_path.read_bytes()).hexdigest().lower()
        except OSError as exc:
            self.last_detail = f"Unable to read bundled installer: {exc}"
            return False

        if digest != self.INSTALLER_SHA256:
            self.last_detail = "Bundled PawnIO installer hash does not match the pinned release."
            return False
        if not self._verify_authenticode(self.installer_path):
            self.last_detail = "Bundled PawnIO installer signature is not trusted by Windows."
            return False
        return True

    @staticmethod
    def _extract_image_path(raw_value: str | None) -> Path | None:
        if not raw_value:
            return None
        expanded = os.path.expandvars(str(raw_value)).strip()
        if expanded.lower().startswith("\\systemroot\\"):
            expanded = os.path.join(
                os.environ.get("SystemRoot", r"C:\Windows"),
                expanded[len("\\SystemRoot\\"):],
            )
        elif expanded.lower().startswith("\\??\\"):
            expanded = expanded[4:]
        if expanded.startswith('"'):
            match = re.match(r'^"([^"]+\.sys)"', expanded, re.IGNORECASE)
            candidate = match.group(1) if match else expanded.strip('"')
        else:
            candidate = expanded.split()[0]
        try:
            return Path(candidate).resolve(strict=False)
        except (OSError, ValueError):
            return None

    def _legacy_paths(self) -> tuple[Path, ...]:
        return (
            self.app_dir / "bin" / "LibreHardwareMonitorLib.sys",
            self.app_dir / "bin" / "lhm_bridge.sys",
        )

    def migrate_legacy_driver(self) -> PawnIOStatus | None:
        """Remove only the known app-owned legacy driver; refuse ambiguous cleanup."""
        known_paths = {path.resolve(strict=False) for path in self._legacy_paths()}
        legacy_service_names = (
            "R0" + "ANTESPORTS",
            "R0" + "lhm_bridge",
            "R0" + "LibreHardwareMonitorLib",
        )
        for legacy_service_name in legacy_service_names:
            service_subkey = rf"SYSTEM\CurrentControlSet\Services\{legacy_service_name}"
            service_key = self._open_machine_key(service_subkey)
            service_image = None
            service_present = service_key is not None
            if service_key is not None:
                try:
                    service_image, _ = winreg.QueryValueEx(service_key, "ImagePath")
                except OSError:
                    service_image = None
                finally:
                    winreg.CloseKey(service_key)

            if not service_present:
                continue
            if service_image is None:
                self.last_detail = "The legacy sensor service has no image path and was not changed."
                return PawnIOStatus.LEGACY_BLOCKED

            resolved_image = self._extract_image_path(service_image)
            if resolved_image not in known_paths:
                self.last_detail = "The legacy sensor service points outside this application and was not changed."
                return PawnIOStatus.LEGACY_BLOCKED

            if not resolved_image.is_file() or self._sha256(resolved_image) != self.LEGACY_DRIVER_SHA256:
                self.last_detail = "The legacy sensor service file did not match the known legacy artifact."
                return PawnIOStatus.LEGACY_BLOCKED

            stop_result = subprocess.run(
                ["sc.exe", "stop", legacy_service_name],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            if stop_result.returncode not in (0, 1060, 1062, 1072):
                self.last_detail = "Unable to stop the known legacy sensor service."
                return PawnIOStatus.LEGACY_CLEANUP_FAILED

            delete_result = subprocess.run(
                ["sc.exe", "delete", legacy_service_name],
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            if delete_result.returncode not in (0, 1060, 1072):
                self.last_detail = "Unable to remove the known legacy sensor service."
                return PawnIOStatus.LEGACY_CLEANUP_FAILED
            time.sleep(0.25)

        for path in self._legacy_paths():
            if not path.exists():
                continue
            if self._sha256(path) != self.LEGACY_DRIVER_SHA256:
                self.last_detail = f"Unexpected legacy driver content was found at {path}."
                return PawnIOStatus.LEGACY_BLOCKED
            try:
                path.unlink()
            except OSError as exc:
                self.last_detail = f"Unable to remove legacy driver {path}: {exc}"
                return PawnIOStatus.LEGACY_CLEANUP_FAILED

        return None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest().lower()

    def _run_installer(self) -> int | None:
        try:
            completed = subprocess.run(
                [str(self.installer_path), "-install", "-silent"],
                cwd=str(self.app_dir),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=180,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
            if completed.stdout:
                self.last_detail = completed.stdout.strip()[-1000:]
            return completed.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.last_detail = f"PawnIO installer failed to run: {exc}"
            return None

    def ensure_ready(self) -> PawnIOStatus:
        migration_status = self.migrate_legacy_driver()
        if migration_status is not None:
            return migration_status

        installed = self.installed_info()
        installed_version = self._version_tuple(installed.version)
        if (
            installed.service_present
            and installed_version >= self.MINIMUM_VERSION
            and installed.driver_signed is not False
        ):
            self.last_detail = f"PawnIO {installed.version} is installed."
            return PawnIOStatus.READY

        if installed_version:
            if installed.service_present and installed.driver_signed is False:
                self.last_detail = "Installed PawnIO driver signature is not trusted."
            elif installed.service_present:
                self.last_detail = f"Installed PawnIO {installed.version} is older than 2.2.0."
            else:
                self.last_detail = "PawnIO is registered but its service is missing."
            if not self._is_admin():
                return PawnIOStatus.NOT_ELEVATED
        elif not self._is_admin():
            self.last_detail = "Administrator privileges are required to install PawnIO."
            return PawnIOStatus.NOT_ELEVATED

        if not self.verify_installer():
            return PawnIOStatus.INVALID_PACKAGE

        exit_code = self._run_installer()
        if exit_code in (3010, 1641):
            self.last_detail = "PawnIO installed and Windows requested a restart."
            return PawnIOStatus.REBOOT_REQUIRED
        if exit_code not in (0,):
            self.last_detail = self.last_detail or f"PawnIO installer exited with code {exit_code}."
            return PawnIOStatus.INSTALL_FAILED

        time.sleep(0.5)
        if self.is_ready():
            self.last_detail = "PawnIO installation verified."
            return PawnIOStatus.READY

        self.last_detail = "PawnIO installer completed but the installation was not detected."
        return PawnIOStatus.REBOOT_REQUIRED
