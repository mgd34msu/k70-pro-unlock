#!/usr/bin/env python3
"""Patch the captured init_boot on the named, stock Android tablet; never flash."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

from k70 import ROOT, PROFILE, LOCK, checked_file, sha256, require, magisk_image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, help="Target serial from adb devices; never guesses a device")
    parser.add_argument("--stock", type=Path, default=ROOT / "work/stock")
    parser.add_argument("--out", type=Path, default=ROOT / "work/patched")
    args = parser.parse_args()
    require(re.fullmatch(r"[A-Za-z0-9._:-]+", args.serial), "Invalid ADB serial")
    stock = checked_file(args.stock / "init_boot_a.img", 0x800000, PROFILE["stock"]["init_boot_a.img"]["sha256"])
    apk = ROOT / "work/tools/Magisk-v30.7.apk"
    spec = LOCK["downloads"][apk.name]
    checked_file(apk, spec["size"], spec["sha256"])
    adb = ["adb", "-s", args.serial]

    def run(*command, **kwargs):
        return subprocess.run(adb + list(command), check=True, **kwargs)

    def shell(command):
        return subprocess.check_output(adb + ["shell", command], text=True).strip()

    require(shell("getprop ro.build.fingerprint") == PROFILE["fingerprint"], "Unsupported target fingerprint")
    require(shell("getprop ro.product.model") == PROFILE["model"], "Unexpected target model")
    require(shell("getprop ro.boot.slot_suffix") == "_a", "Only active slot a was hardware-tested")
    require(shell("getprop ro.bootmode") == "normal", "Patch from normal Android, before changing its boot chain")
    args.out.mkdir(parents=True, exist_ok=True)
    require(not (args.out / "init_boot-magisk.img").exists(), "Magisk output already exists")
    remote = "/data/local/tmp/k70-magisk-patch"
    run("shell", f"mkdir -p {remote}")
    entries = {"boot_patch.sh": "assets/boot_patch.sh", "util_functions.sh": "assets/util_functions.sh", "stub.apk": "assets/stub.apk"}
    for name in ("busybox", "magiskboot", "magiskinit", "magisk", "init-ld"):
        entries[name] = f"lib/arm64-v8a/lib{name}.so"
    with tempfile.TemporaryDirectory(prefix="k70-magisk-") as tmp:
        directory = Path(tmp)
        with zipfile.ZipFile(apk) as archive:
            for name, entry in entries.items():
                path = directory / name
                path.write_bytes(archive.read(entry))
                run("push", str(path), f"{remote}/{name}")
        original = directory / "init_boot-stock.img"
        original.write_bytes(stock)
        run("push", str(original), f"{remote}/init_boot-stock.img")
    # Same settings and on-device patcher used in the successful session.
    run("shell", f"cd {remote} && chmod 755 busybox magiskboot magiskinit magisk init-ld && "
        "BOOTMODE=true KEEPVERITY=true KEEPFORCEENCRYPT=true PATCHVBMETAFLAG=false "
        "./busybox sh boot_patch.sh init_boot-stock.img")
    remote_hash = shell(f"sha256sum {remote}/new-boot.img").split()[0]
    run("shell", f"mkdir -p {remote}/verify")
    run("shell", f"cd {remote}/verify && ../magiskboot unpack ../new-boot.img")
    status = subprocess.run(adb + ["shell", f"cd {remote}/verify && ../magiskboot cpio ramdisk.cpio test"]).returncode
    require(status == 1, f"Magisk ramdisk test returned {status}; expected 1")
    output = args.out / "init_boot-magisk.img"
    run("pull", f"{remote}/new-boot.img", str(output))
    data = checked_file(output, 0x800000, remote_hash)
    report = {"target_serial": args.serial, "fingerprint": PROFILE["fingerprint"], "stock_sha256": sha256(stock),
              "apk_sha256": spec["sha256"], "patched_sha256": sha256(data), "ramdisk_test_status": status,
              "settings": {"KEEPVERITY": True, "KEEPFORCEENCRYPT": True, "PATCHVBMETAFLAG": False}, "flashed": False}
    (args.out / "magisk-preparation.json").write_text(json.dumps(report, indent=2) + "\n")
    magisk_image(args.out)
    print(f"Prepared {output}; no partition was flashed. Keep its report with the image.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        sys.exit(1)
