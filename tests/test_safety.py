"""Offline checks: no hardware, credentials, or proprietary firmware fixtures."""
import copy
import json
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import k70


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_hash_and_size_both_required(self):
        path = self.root / "capture"
        path.write_bytes(b"original")
        digest = k70.sha256(b"original")
        self.assertEqual(k70.checked_file(path, 8, digest), b"original")
        with self.assertRaisesRegex(ValueError, "wrong size"):
            k70.checked_file(path, 9, digest)
        path.write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            k70.checked_file(path, 8, digest)

    def test_prepare_rejects_unknown_stock_before_tools_or_output(self):
        stock = self.root / "stock"
        stock.mkdir()
        (stock / "splloader.img").write_bytes(bytes(0x400000))
        out = self.root / "output"
        with patch.object(k70, "check_tools") as tools:
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                k70.prepare(stock, out, self.root / "tools")
            tools.assert_not_called()
        self.assertFalse(out.exists())

    def test_wipe_request_preserves_slot_and_vendor_metadata(self):
        stock = random.Random(70).randbytes(0x100000)
        result = k70.wipe_request(stock)
        self.assertEqual(result[2048:], stock[2048:])
        self.assertEqual(result[:32], b"boot-recovery".ljust(32, b"\0"))
        args = result[64:832].rstrip(b"\0").splitlines()
        self.assertEqual(args, [b"recovery", b"--wipe_data", b"--reason=bootloader_unlock", b"--locale=en_US"])
        self.assertEqual(result[32:64], bytes(32))
        self.assertEqual(result[832:2048], bytes(1216))
        with self.assertRaises(ValueError):
            k70.wipe_request(stock[:-1])

    def test_wipe_is_explicit_and_guard_survives_python_optimization(self):
        result = subprocess.run([sys.executable, "-O", str(ROOT / "scripts/k70.py"),
                                 "make-wipe-request", "--out", str(self.root / "out")], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--wipe-data", result.stderr)
        self.assertFalse((self.root / "out").exists())

    def test_backup_command_plan_is_read_only_and_never_resets(self):
        plan = k70.command_plan("backup", self.root / "stock", self.root / "out", self.root / "readback")
        self.assertEqual(len(plan), 11)
        self.assertTrue(all(line.startswith(("path ", "read_part ")) for line in plan))
        self.assertIn("read_part splloader_bak 0 0x400000 splloader_bak.img", plan)
        self.assertIn("read_part init_boot_b 0 0x800000 init_boot_b.img", plan)
        (self.root / "stock/previous-capture").write_text("keep me")
        with self.assertRaisesRegex(ValueError, "must be empty"):
            k70.command_plan("backup", self.root / "stock", self.root / "out", self.root / "readback")

    def test_interactive_plan_refuses_whitespace_paths(self):
        with self.assertRaisesRegex(ValueError, "whitespace"):
            k70.command_plan("backup", self.root / "my stock", self.root / "out", self.root / "readback")

    def test_magisk_report_cannot_accept_unmodified_image(self):
        payload = bytearray(0x800000)
        payload[:8] = b"ANDROID!"
        struct.pack_into("<I", payload, 12, 1024)
        struct.pack_into("<I", payload, 40, 4)
        digest = k70.sha256(payload)
        (self.root / "init_boot-magisk.img").write_bytes(payload)
        report = {"stock_sha256": digest, "apk_sha256": k70.LOCK["downloads"]["Magisk-v30.7.apk"]["sha256"],
                  "patched_sha256": digest, "ramdisk_test_status": 1}
        (self.root / "magisk-preparation.json").write_text(json.dumps(report))
        profile = copy.deepcopy(k70.PROFILE)
        profile["stock"]["init_boot_a.img"]["sha256"] = digest
        with patch.object(k70, "PROFILE", profile):
            with self.assertRaisesRegex(ValueError, "unmodified"):
                k70.magisk_image(self.root)

    def test_complete_readback_rejects_bad_second_copy(self):
        expected = {"uboot_a.img": b"same image", "uboot_b.img": b"same image"}
        for name, data in expected.items():
            (self.root / name).write_bytes(data)
        (self.root / "uboot_b.img").write_bytes(b"wrong copy")
        with patch.object(k70, "stage_images", return_value=expected), patch.object(sys, "argv", [
                "k70.py", "verify-readback", "--stage", "unlock", "--readback", str(self.root)]):
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                k70.main()

    def test_profile_offsets_are_consistent_with_hardware_patch(self):
        self.assertEqual(tuple(k70.PROFILE["spl"]["verify_sites_file_offsets"]), k70.SITES)
        self.assertEqual(k70.PROFILE["spl"]["verify_target_file_offset"], 0xB150)
        self.assertEqual(k70.PROFILE["uboot"]["load_base"], 0x9F000000)
        self.assertEqual(k70.PROFILE["uboot"]["lock_patch_payload_offset"], 0x61814)
        self.assertEqual(k70.PROFILE["uboot"]["original_word"], 0xD2800001)
        self.assertEqual(k70.PROFILE["uboot"]["replacement_word"], 0x1400000B)


if __name__ == "__main__":
    unittest.main()
