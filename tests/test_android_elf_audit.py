"""ELF target verification must use headers, not filenames."""
import tempfile
import unittest
from pathlib import Path

from scripts.audit_android_python_bundle import audit_bundle, elf_machine


def fake_elf(machine):
    payload = bytearray(20)
    payload[:4] = b"\x7fELF"
    payload[4] = 2
    payload[5] = 1
    payload[18:20] = machine.to_bytes(2, "little")
    return bytes(payload)


class AndroidRuntimeElfTests(unittest.TestCase):
    def test_filename_x86_does_not_override_aarch64_machine(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "python.cpython-314-x86_64-linux-gnu.so"
            path.write_bytes(fake_elf(183))
            self.assertEqual(elf_machine(path), 183)

    def test_bytecode_only_fallback_is_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "PySide6").mkdir()
            (root / "charset_normalizer").mkdir()
            (root / "charset_normalizer" / "md.pyc").write_bytes(b"fixture")
            (root / "PySide6" / "QtWidgets.abi3.so").write_bytes(fake_elf(183))
            self.assertEqual(audit_bundle(root), 1)

    def test_foreign_binary_fails_release_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "PySide6").mkdir()
            (root / "charset_normalizer").mkdir()
            (root / "charset_normalizer" / "md.py").write_text("")
            (root / "PySide6" / "QtWidgets.abi3.so").write_bytes(fake_elf(183))
            (root / "charset_normalizer" / "cd.so").write_bytes(fake_elf(62))
            with self.assertRaisesRegex(ValueError, "charset_normalizer/cd.so"):
                audit_bundle(root)

    def test_arm64_only_bundle_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "PySide6").mkdir()
            (root / "charset_normalizer").mkdir()
            (root / "charset_normalizer" / "md.py").write_text("")
            (root / "PySide6" / "QtWidgets.abi3.so").write_bytes(fake_elf(183))
            self.assertEqual(audit_bundle(root), 1)


if __name__ == "__main__":
    unittest.main()
