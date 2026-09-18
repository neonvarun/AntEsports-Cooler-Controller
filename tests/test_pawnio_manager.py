import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.pawnio_manager import (
    PawnIOInstallation,
    PawnIOManager,
    PawnIOStatus,
)


class PawnIOManagerTests(unittest.TestCase):
    def test_invalid_installer_hash_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "bin").mkdir()
            installer = root / "bin" / "PawnIO_setup.exe"
            installer.write_bytes(b"not-the-pinned-installer")
            manager = PawnIOManager(root)

            self.assertFalse(manager.verify_installer())
            self.assertIn("hash", manager.last_detail.lower())

    def test_invalid_installer_signature_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "bin").mkdir()
            installer = root / "bin" / "PawnIO_setup.exe"
            installer.write_bytes(b"signed-content-fixture")
            manager = PawnIOManager(root)
            manager.INSTALLER_SHA256 = hashlib.sha256(installer.read_bytes()).hexdigest()

            with patch.object(manager, "_verify_authenticode", return_value=False):
                self.assertFalse(manager.verify_installer())
            self.assertIn("signature", manager.last_detail.lower())

    def test_missing_pawnio_requires_elevation(self):
        manager = PawnIOManager(tempfile.mkdtemp())
        with patch.object(manager, "migrate_legacy_driver", return_value=None), \
             patch.object(PawnIOManager, "installed_info", return_value=PawnIOInstallation(None, False)), \
             patch.object(manager, "_is_admin", return_value=False):
            self.assertEqual(manager.ensure_ready(), PawnIOStatus.NOT_ELEVATED)

    def test_version_without_service_is_not_ready(self):
        with patch.object(
            PawnIOManager,
            "installed_info",
            return_value=PawnIOInstallation("2.2.0.0", False),
        ):
            self.assertFalse(PawnIOManager.is_ready())

    def test_untrusted_installed_driver_is_not_ready(self):
        manager = PawnIOManager(tempfile.mkdtemp())
        with patch.object(manager, "migrate_legacy_driver", return_value=None), \
             patch.object(
                 PawnIOManager,
                 "installed_info",
                 return_value=PawnIOInstallation("2.2.0.0", True, driver_signed=False),
             ), \
             patch.object(manager, "_is_admin", return_value=False):
            self.assertFalse(PawnIOManager.is_ready())
            self.assertEqual(manager.ensure_ready(), PawnIOStatus.NOT_ELEVATED)
            self.assertIn("signature", manager.last_detail.lower())

    def test_installer_reboot_result_is_reported(self):
        manager = PawnIOManager(tempfile.mkdtemp())
        with patch.object(manager, "migrate_legacy_driver", return_value=None), \
             patch.object(PawnIOManager, "installed_info", return_value=PawnIOInstallation(None, False)), \
             patch.object(manager, "_is_admin", return_value=True), \
             patch.object(manager, "verify_installer", return_value=True), \
             patch.object(manager, "_run_installer", return_value=3010):
            self.assertEqual(manager.ensure_ready(), PawnIOStatus.REBOOT_REQUIRED)

    def test_known_legacy_file_is_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "bin").mkdir()
            legacy = root / "bin" / "lhm_bridge.sys"
            legacy.write_bytes(b"known-legacy-driver")
            manager = PawnIOManager(root)
            manager.LEGACY_DRIVER_SHA256 = hashlib.sha256(legacy.read_bytes()).hexdigest()

            self.assertIsNone(manager.migrate_legacy_driver())
            self.assertFalse(legacy.exists())

    def test_legacy_service_outside_app_is_refused(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = PawnIOManager(temp_dir)
            fake_key = object()
            with patch.object(manager, "_open_machine_key", return_value=fake_key), \
                 patch("src.pawnio_manager.winreg.QueryValueEx", return_value=(r"C:\\Windows\\System32\\drivers\\other.sys", 1)), \
                 patch("src.pawnio_manager.winreg.CloseKey"):
                self.assertEqual(manager.migrate_legacy_driver(), PawnIOStatus.LEGACY_BLOCKED)

    def test_known_legacy_service_is_stopped_and_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "bin").mkdir()
            legacy = root / "bin" / "lhm_bridge.sys"
            legacy.write_bytes(b"known-legacy-driver")
            manager = PawnIOManager(root)
            manager.LEGACY_DRIVER_SHA256 = hashlib.sha256(legacy.read_bytes()).hexdigest()
            fake_key = object()

            with patch.object(manager, "_open_machine_key", return_value=fake_key), \
                 patch("src.pawnio_manager.winreg.QueryValueEx", return_value=(str(legacy), 1)), \
                 patch("src.pawnio_manager.winreg.CloseKey"), \
                 patch("src.pawnio_manager.subprocess.run", return_value=type("Result", (), {"returncode": 0})()) as run:
                self.assertIsNone(manager.migrate_legacy_driver())

            self.assertFalse(legacy.exists())
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(len(commands), 6)
            self.assertTrue(all(command[:2] in (["sc.exe", "stop"], ["sc.exe", "delete"]) for command in commands))

    def test_image_path_parser_handles_kernel_prefix_and_quotes(self):
        path = PawnIOManager._extract_image_path(
            r'\??\"C:\\App\\bin\\lhm_bridge.sys"'
        )
        self.assertIsNotNone(path)
        self.assertTrue(str(path).lower().endswith("lhm_bridge.sys"))


if __name__ == "__main__":
    unittest.main()
