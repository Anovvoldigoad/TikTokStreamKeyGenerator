"""Fail Android packaging if any bundled ELF module targets the wrong CPU.

Filename tags are not reliable for cross-compilation: a .so named x86_64
may contain AArch64 machine code. Inspect ELF e_machine instead.
"""
import argparse
from pathlib import Path


ELF_AARCH64 = 183


def elf_machine(path):
    with Path(path).open("rb") as stream:
        header = stream.read(20)
    if header[:4] != b"\x7fELF":
        raise ValueError(f"Not an ELF shared library: {path}")
    if len(header) < 20 or header[5] not in (1, 2):
        raise ValueError(f"Invalid ELF header: {path}")
    order = "little" if header[5] == 1 else "big"
    return int.from_bytes(header[18:20], byteorder=order)


def audit_bundle(root):
    root = Path(root)
    if not (root / "PySide6" / "QtWidgets.abi3.so").is_file():
        raise ValueError("Android PySide6 QtWidgets is missing")
    if not (root / "charset_normalizer" / "md.py").is_file():
        raise ValueError("charset-normalizer pure-Python fallback is missing")
    checked = 0
    wrong = []
    for path in sorted(root.rglob("*.so")):
        machine = elf_machine(path)
        checked += 1
        if machine != ELF_AARCH64:
            wrong.append(f"{path.relative_to(root)}: ELF e_machine={machine} (expected {ELF_AARCH64})")
    if wrong:
        raise ValueError("Foreign-architecture native modules in Android Python bundle:\n"
                         + "\n".join(wrong))
    return checked


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle_dir")
    args = parser.parse_args()
    count = audit_bundle(args.bundle_dir)
    print(f"Android Python native extension audit PASS: {count} AArch64 ELF modules")


if __name__ == "__main__":
    main()
