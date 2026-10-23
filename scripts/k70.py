#!/usr/bin/env python3
"""Offline, exact-build preparation and command generation. Never opens USB."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
PROFILE = json.loads((ROOT / "profiles/k70-pro-us-a16-20260912.json").read_text())
LOCK = json.loads((ROOT / "tools.lock.json").read_text())
SITES = (0xAE10, 0xAF20, 0xB060, 0xB094, 0xB0C4)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def word(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def checked_file(path, size=None, digest=None):
    data = path.read_bytes()
    require(size is None or len(data) == size, f"{path}: wrong size ({len(data)})")
    require(digest is None or sha256(data) == digest, f"{path}: SHA256 mismatch; unsupported or modified input")
    return data


def check_stock(directory):
    return {name: checked_file(directory / name, spec["size"], spec.get("sha256"))
            for name, spec in PROFILE["stock"].items()}


def check_tools(directory):
    for name, spec in LOCK["downloads"].items():
        checked_file(directory / name, spec["size"], spec["sha256"])
    for name, spec in LOCK["repositories"].items():
        repo = directory / name
        rev = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        require(rev == spec["commit"], f"{repo}: unexpected source revision")
        changes = subprocess.check_output(["git", "-C", str(repo), "diff", "HEAD", "--"], text=True)
        require(not changes, f"{repo}: tracked source has local modifications")
        require((repo / spec["binary"]).is_file(), f"{repo}: build tool first")


def patch_spl_payload(stock):
    size = word(stock, 0x30)
    require(stock[:4] == b"DHTB" and size == 0xF7F0, "Unexpected SPL header")
    require(stock[8:40] == hashlib.sha256(stock[0x200:0x200 + size]).digest(), "Invalid stock SPL payload hash")
    matches = []
    for off in range(0x204, 0x200 + size - 12, 4):
        if word(stock, off) == 0x34000060 and word(stock, off - 4) >> 8 == 0x940000 and word(stock, off + 4) >> 16 == 0x5280:
            matches.append(off - 4)
    require(tuple(matches) == SITES, f"Unexpected SPL verification sites: {matches}")
    result = bytearray(stock)
    for off in SITES:
        require(off + (word(stock, off) & 0x03FFFFFF) * 4 == 0xB150, "Unexpected verify function")
        require(word(stock, off + 12) >> 26 == 0x25, "Unexpected failure call")
        result[off:off + 16] = struct.pack("<I", 0xD503201F) * 4
    return result


def emulate_lock(payload, expected):
    from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE
    from unicorn.arm64_const import UC_ARM64_REG_X0, UC_ARM64_REG_X30, UC_ARM64_REG_SP, UC_ARM64_REG_PC
    base, buffer, stack, stop = 0x9F000000, 0xA0000000, 0xA0100000, 0xA0200000
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for address, size in ((base, 0x200000), (buffer, 0x1000), (stack, 0x2000), (stop, 0x1000)):
        uc.mem_map(address, size)
    uc.mem_write(base, bytes(payload))
    uc.reg_write(UC_ARM64_REG_SP, stack + 0x1000)
    uc.reg_write(UC_ARM64_REG_X30, stop)
    calls = []
    stubs = {base + 0x2FC50: buffer, base + 0x33664: buffer,
             base + 0x5F344: 0, base + 0x2FDC0: 0, base + 0x326B4: 0}

    def hook(machine, address, size, user_data):
        if address in stubs:
            calls.append(address)
            machine.reg_write(UC_ARM64_REG_X0, stubs[address])
            machine.reg_write(UC_ARM64_REG_PC, machine.reg_read(UC_ARM64_REG_X30))

    uc.hook_add(UC_HOOK_CODE, hook)
    uc.emu_start(base + 0x617B4, stop, timeout=1000000, count=20000)
    require(uc.reg_read(UC_ARM64_REG_PC) == stop, "Emulated function did not return")
    require(uc.reg_read(UC_ARM64_REG_X0) == expected, "Unexpected emulated lock return")
    require(word(bytes(uc.mem_read(base + 0x1228C8, 4)), 0) == expected, "Unexpected lock global")
    require(base + 0x2FDC0 in calls, "Expected cleanup did not run")


def prepare(stock_dir, out, tools):
    stock = check_stock(stock_dir)
    check_tools(tools)
    require(not out.exists() or not any(out.iterdir()), f"{out}: use a new/empty output directory")
    spl = stock["splloader.img"]
    unsigned = patch_spl_payload(spl)
    size = word(spl, 0x30)
    with tempfile.TemporaryDirectory(prefix="k70-spl-") as tmp:
        working = Path(tmp) / "spl.bin"
        working.write_bytes(unsigned)
        subprocess.run([str(tools / "spl-exploit/patcher"), str(tools / "spl-exploit/cfg/ums512.cfg"), str(working)], check=True)
        combined = bytearray(working.read_bytes())
    require(combined[0x200:0x200 + size] == unsigned[0x200:0x200 + size], "SPL exploit changed executable payload")
    combined[8:40] = hashlib.sha256(combined[0x200:0x200 + size]).digest()
    cert_off = struct.unpack_from("<Q", combined, 0x200 + size + 0x28)[0]
    donor = (tools / "fdl1-dl.bin").read_bytes()
    donor_off = struct.unpack_from("<Q", donor, 0x200 + word(donor, 0x30) + 0x28)[0]
    cert, donor_cert = combined[cert_off:], donor[donor_off:]
    require(word(cert, 4) == word(donor_cert, 4) == 0xDC40, "Unexpected exploit key length")
    require(cert[0xC:0x10C] == donor_cert[0xC:0x10C], "Exploit modulus differs from working FDL1")
    require(len(combined) <= 0x40000, "SPL exploit exceeds boot image region")
    combined.extend(spl[len(combined):])

    ub = bytearray(stock["uboot_a.img"])
    require(word(ub, 0x200 + 0x61814) == 0xD2800001, "Unexpected lock instruction")
    require(struct.unpack_from("<4I", ub, 0x200 + 0x61840) == (0x52800020, 0x2A0003F5, 0xB908CA80, 0x17FFFFEB), "Unexpected unlocked block")
    struct.pack_into("<I", ub, 0x200 + 0x61814, 0x1400000B)
    ub_size = word(ub, 0x30)
    ub[8:40] = hashlib.sha256(ub[0x200:0x200 + ub_size]).digest()
    emulate_lock(stock["uboot_a.img"][0x200:0x200 + ub_size], 0)
    emulate_lock(ub[0x200:0x200 + ub_size], 1)
    outputs = {"splloader-unlocked.img": combined, "uboot-unlocked.img": ub}
    for name, data in outputs.items():
        require(sha256(data) == PROFILE["patched"][name], f"{name}: output differs from hardware-tested image")
    # No permanent output is created until every compatibility/emulation check passes.
    out.mkdir(parents=True, exist_ok=True)
    for name, data in outputs.items():
        (out / name).write_bytes(data)
    (out / "preparation.json").write_text(json.dumps({
        "build": PROFILE["build"], "spl_verify_sites": [hex(x) for x in SITES],
        "stock_and_patched_lock_emulation": "passed", "exploit_modulus_matches_working_fdl1": True,
        "images": {name: sha256(data) for name, data in outputs.items()},
        "hardware_accessed": False,
    }, indent=2) + "\n")


def wipe_request(stock):
    require(len(stock) == 0x100000, "misc must be a full 1 MiB partition capture")
    result = bytearray(stock)
    result[:2048] = bytes(2048)
    result[:32] = b"boot-recovery".ljust(32, b"\0")
    args = b"recovery\n--wipe_data\n--reason=bootloader_unlock\n--locale=en_US\n"
    result[64:832] = args.ljust(768, b"\0")
    require(result[2048:] == stock[2048:], "A/B or vendor metadata changed")
    return result


def magisk_image(directory):
    report = json.loads((directory / "magisk-preparation.json").read_text())
    require(report["stock_sha256"] == PROFILE["stock"]["init_boot_a.img"]["sha256"], "Wrong Magisk source")
    require(report["apk_sha256"] == LOCK["downloads"]["Magisk-v30.7.apk"]["sha256"], "Wrong Magisk release")
    data = checked_file(directory / "init_boot-magisk.img", 0x800000, report["patched_sha256"])
    require(data[:8] == b"ANDROID!" and word(data, 40) == 4, "Expected Android boot header v4")
    require(word(data, 8) == 0 and word(data, 12) > 0, "Expected init_boot with a ramdisk and no kernel")
    require(sha256(data) != report["stock_sha256"], "Magisk image is unmodified")
    require(report["ramdisk_test_status"] == 1, "Missing Magisk ramdisk verification")
    return data


def stage_images(stage, stock, out):
    if stage == "unlock":
        spl = checked_file(out / "splloader-unlocked.img", 0x400000, PROFILE["patched"]["splloader-unlocked.img"])
        ub = checked_file(out / "uboot-unlocked.img", 0x300000, PROFILE["patched"]["uboot-unlocked.img"])
        return {"splloader.img": spl, "splloader_bak.img": spl, "uboot_a.img": ub, "uboot_b.img": ub}
    if stage == "magisk":
        img = magisk_image(out)
        return {"init_boot_a.img": img, "init_boot_b.img": img}
    if stage == "wipe":
        expected = wipe_request(checked_file(stock / "misc.img", 0x100000))
        checked_file(out / "misc-wipe-request.img", 0x100000, sha256(expected))
        return {"misc.img": expected}
    if stage == "restore":
        data = check_stock(stock)
        return {name: data[name] for name in ("init_boot_a.img", "init_boot_b.img", "uboot_a.img", "uboot_b.img", "splloader.img", "splloader_bak.img")}
    raise ValueError(f"Unknown stage: {stage}")


def command_plan(stage, stock, out, readback):
    for p in (stock, out, readback):
        require(not any(c.isspace() for c in str(p)), "spd_dump interactive paths must not contain whitespace")
    if stage == "backup":
        stock.mkdir(parents=True, exist_ok=True)
        require(not any(stock.iterdir()), "Backup destination must be empty; keep previous captures")
        return [f"path {stock}"] + [f"read_part {Path(name).stem} 0 {spec['size']:#x} {name}" for name, spec in PROFILE["stock"].items()]
    check_stock(stock)
    images = stage_images(stage, stock, out)
    require(not readback.exists() or not any(readback.iterdir()), "Readback directory must be empty")
    readback.mkdir(parents=True, exist_ok=True)
    plans = {
        "unlock": [("splloader", out / "splloader-unlocked.img"), ("uboot_a", out / "uboot-unlocked.img")],
        "magisk": [("init_boot_a", out / "init_boot-magisk.img")],
        "wipe": [("misc", out / "misc-wipe-request.img")],
        "restore": [("init_boot_a", stock / "init_boot_a.img"), ("uboot_a", stock / "uboot_a.img"), ("splloader", stock / "splloader.img")],
    }
    lines = [f"path {readback}"]
    for part, path in plans[stage]:
        lines.append(f"write_part {part} {path}")
    for name, data in images.items():
        lines.append(f"read_part {Path(name).stem} 0 {len(data):#x} {name}")
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check-stock", "check-tools", "prepare", "make-wipe-request", "commands", "verify-readback"])
    parser.add_argument("--stock", type=Path, default=ROOT / "work/stock")
    parser.add_argument("--out", type=Path, default=ROOT / "work/patched")
    parser.add_argument("--tools", type=Path, default=ROOT / "work/tools")
    parser.add_argument("--readback", type=Path)
    parser.add_argument("--stage", choices=["backup", "unlock", "magisk", "wipe", "restore"])
    parser.add_argument("--wipe-data", action="store_true", help="Required to prepare a recovery factory-reset request")
    args = parser.parse_args()
    stock, out, tools = args.stock.resolve(), args.out.resolve(), args.tools.resolve()
    if args.action == "check-stock":
        data = check_stock(stock)
        (stock / "SHA256SUMS").write_text("".join(f"{sha256(value)}  {name}\n" for name, value in data.items()))
        print("All stock partitions match the supported build. Keep this backup off-device.")
    elif args.action == "check-tools":
        check_tools(tools)
        print("Pinned tool sources and downloads verified.")
    elif args.action == "prepare":
        prepare(stock, out, tools)
        print("Exact hardware-tested SPL/UBoot outputs reproduced; lock-function emulation passed.")
    elif args.action == "make-wipe-request":
        require(args.wipe_data, "Pass --wipe-data to prepare a request that erases apps, accounts and local files")
        check_stock(stock)
        out.mkdir(parents=True, exist_ok=True)
        target = out / "misc-wipe-request.img"
        require(not target.exists(), "Wipe request already exists")
        target.write_bytes(wipe_request((stock / "misc.img").read_bytes()))
        print("Recovery wipe request prepared; A/B and vendor metadata beyond the BCB preserved.")
    else:
        require(args.stage is not None, "--stage is required")
        readback = (args.readback or ROOT / f"work/readback-{args.stage}").resolve()
        if args.action == "commands":
            print("\n".join(command_plan(args.stage, stock, out, readback)))
        else:
            require(args.stage != "backup", "Use check-stock to verify backups")
            for name, expected in stage_images(args.stage, stock, out).items():
                checked_file(readback / name, len(expected), sha256(expected))
            print(f"{args.stage}: all full readbacks match, including both copies where applicable.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, struct.error, ImportError, subprocess.CalledProcessError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        sys.exit(1)
