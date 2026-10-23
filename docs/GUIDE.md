# Step-by-step guide

Read the [compatibility table](../README.md#supported-hardware-and-firmware) and [recovery procedure](RECOVERY.md) first. This is the successful sequence for one exact build, with the failed experiments removed. The packaging scripts were subsequently checked offline against the saved original images; the newly packaged scripts have not been run through another complete physical-tablet installation.

Commands marked **host** go in the Linux terminal. Commands printed for **`FDL2>`** go in the interactive loader. Never pipe an unchecked transcript into the flasher.

## 1. Prepare the computer and identify the tablet

Install Python 3.10+, Git, a C compiler, Make, libusb development headers, ADB, and fastboot. For Debian/Ubuntu:

```bash
sudo apt install git build-essential libusb-1.0-0-dev python3 python3-venv adb fastboot
```

For Arch Linux:

```bash
sudo pacman -S --needed base-devel git libusb python android-tools
```

Clone into a path **without whitespace**; the tested old flasher's interactive parser splits on whitespace.

```bash
git clone https://github.com/mgd34msu/k70-pro-unlock.git
cd k70-pro-unlock
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
python3 scripts/fetch-tools.py
```

The downloader verifies the two FDLs and Magisk APK by hash and builds two upstream C programs from pinned commits. It does not communicate with the tablet. Do not substitute a newer flasher or a different FDL pair just because the filenames look similar.

Finish stock Android setup, enable Developer options and USB debugging, and authorize the computer. Check the target:

```bash
adb devices -l
export SERIAL='YOUR_TABLET_SERIAL'
adb -s "$SERIAL" shell 'getprop ro.product.model; getprop ro.board.platform; getprop ro.build.fingerprint; getprop ro.boot.slot_suffix'
```

Expected: `K70_PRO`, `ums512`, the supported fingerprint, and `_a`. Always use `-s "$SERIAL"` with ADB and fastboot; other connected Android devices are not targets. BootROM selection works differently: disconnect other Unisoc USB devices.

## 2. Enter BootROM and capture the originals

On the **host**, generate the backup commands before opening the loader:

```bash
python3 scripts/k70.py commands --stage backup > work/backup.commands
cat work/backup.commands
bash scripts/bootrom.sh
```

The loader waits for 180 seconds. Enter BootROM using either method:

- **Tablet powered off:** unplug USB, hold **Volume Down alone**, and reconnect USB.
- **Tablet running or stuck:** keep USB connected, hold **Volume Down + Power for 10 seconds**, then **release Power** while continuing to hold Volume Down.

At the host, expect `SPRD3`, FDL1 transfer, FDL2 transfer, a partition table, and finally `FDL2>`. A timeout followed by successful `CHECK_BAUD FDL1`, and a timeout before `DISABLE_TRANSCODE`, occurred in the working session. Continue only if the loader actually reaches `FDL2>` and lists the expected eMMC partitions.

**Release Volume Down once `FDL2>` is ready.** Holding Power through loader startup can reset the tablet.

Paste the contents of `work/backup.commands` into **`FDL2>`**. It reads:

| Partition | Full size |
| --- | --- |
| `splloader`, `splloader_bak` | 4 MiB each |
| `uboot_a`, `uboot_b` | 3 MiB each |
| `init_boot_a`, `init_boot_b` | 8 MiB each |
| `vbmeta_a`, `vbmeta_b` | 1 MiB each |
| `misc`, `miscdata` | 1 MiB each |

Wait until every read has completed and `FDL2>` returns. In a **second host terminal**, from the repository directory:

```bash
python3 scripts/k70.py check-stock
```

This checks complete partition sizes and the build-specific hashes, then writes `work/stock/SHA256SUMS`. `misc` and `miscdata` are size-checked and hashed for your own backup, not compared with another tablet's contents. Copy `work/stock/` somewhere safe off the tablet.

**A mismatch means stop. Do not patch or flash.** In particular, a trimmed 65 KB SPL capture is not the full 4 MiB backup this guide requires. With the pinned tool, the commands above returned full partitions.

After the stock checks pass, type at **`FDL2>`**:

```text
reset
```

Wait for stock Android to finish starting, then check from the **host**:

```bash
adb -s "$SERIAL" wait-for-device
adb -s "$SERIAL" shell getprop sys.boot_completed
```

Expected: `1`. This first session changes no partitions.

## 3. Prepare the exact boot-chain patches and Magisk image

On the **host**:

```bash
.venv/bin/python scripts/k70.py prepare
.venv/bin/python scripts/patch-magisk.py --serial "$SERIAL"
```

Preparation must reproduce these exact outputs:

```text
splloader-unlocked.img
34f221f1b15cd27c6a6bd8c0537d9e82475e3f40596e5e37d9cc30263862d63c

uboot-unlocked.img
68353cbd9cc219135300dd81aa1ccd6ad7cf8c4674502b6c4990a15afea53f3a
```

The first script verifies every original image, checks all five SPL call sites, applies the pinned persistent exploit, compares its modulus with the already-working FDL1, emulates the original and patched U-Boot lock function, and checks the resulting hashes. It creates no image output until those checks pass. It never opens USB.

The second script verifies the connected tablet's model, fingerprint, normal Android mode, and active slot, then extracts the verified Magisk APK and patches your captured `init_boot_a.img` **on that tablet** under `/data/local/tmp/`. It uses the successful settings:

```text
BOOTMODE=true
KEEPVERITY=true
KEEPFORCEENCRYPT=true
PATCHVBMETAFLAG=false
```

It verifies the patched ramdisk using Magisk's own tool, pulls the full 8 MiB image back, and records its hash and target in `work/patched/magisk-preparation.json`. It does not flash or reboot. Follow [Magisk's same-device patching requirement](https://topjohnwu.github.io/Magisk/install.html#patching-images); do not use someone else's patched image. Our historical patched hash is in the profile as a reference, not a requirement for another tablet's generated image.

Run `prepare` before `patch-magisk`: boot-chain preparation requires an empty output directory. Keep the Magisk image and its preparation report together.

## 4. Install the SPL and U-Boot patches

On the **host**:

```bash
python3 scripts/k70.py commands --stage unlock > work/unlock.commands
cat work/unlock.commands
bash scripts/bootrom.sh
```

Use the same physical BootROM procedure. Release Volume Down at `FDL2>`. Paste `work/unlock.commands` into **`FDL2>`**. It writes the prepared SPL and U-Boot, then reads back both SPL copies and both U-Boot slots to `work/readback-unlock/`.

The tested donor FDL2 mirrors these writes: **`write_part uboot_a` also changed `uboot_b`, and `write_part splloader` also changed `splloader_bak`.** Do not treat the other slot as an untouched rescue copy.

Wait for all reads to finish. In the **second host terminal**:

```bash
python3 scripts/k70.py verify-readback --stage unlock
```

Expected: all full readbacks match. Only then type **`FDL2>`**:

```text
reset
```

Our tablet reached Android Recovery with **“Cannot load Android system / data may be corrupt”** after this lock-state change. This was followed by the factory reset below; it was not the earlier black-screen boot failure. If you see recovery, check from the **host**:

```bash
adb devices -l
adb -s "$SERIAL" reboot bootloader
```

The bootloader screen should show:

```text
INFO: LOCK FLAG IS : UNLOCK!!!
```

Recovery's ADB shell failed its SELinux context check on the tested build. `adb reboot bootloader` still worked. Do not depend on a recovery shell. Also, `fastboot getvar unlocked` returned a blank value on this vendor bootloader; the screen and later Android properties were the useful checks.

**Do not flash Magisk with fastboot.** Despite the unlocked screen, this firmware's fastboot write path invoked secure AVB verification and panicked before writing the modified `init_boot`. Use BootROM for the next step.

## 5. Install Magisk through BootROM and request the factory reset

On the **host**, prepare the commands and the standard recovery wipe request:

```bash
python3 scripts/k70.py commands --stage magisk > work/magisk.commands
python3 scripts/k70.py make-wipe-request --wipe-data
python3 scripts/k70.py commands --stage wipe > work/wipe.commands
cat work/magisk.commands
cat work/wipe.commands
bash scripts/bootrom.sh
```

The `--wipe-data` option prepares an instruction that will erase apps, accounts, and local files once recovery runs. It preserves the A/B slot metadata and vendor data after the first 2048 bytes of your own saved `misc` image. Preparing the file alone performs no wipe.

Enter BootROM from fastboot with USB connected: Volume Down + Power for 10 seconds, release Power, keep Volume Down until the loader is ready, then release it.

At **`FDL2>`**, paste `work/magisk.commands`. Wait for all writes and both full readbacks to finish. On the **host**:

```bash
python3 scripts/k70.py verify-readback --stage magisk
```

Both `init_boot` slots must match your generated image and its preparation report. Next paste `work/wipe.commands` into **`FDL2>`**, wait for its readback, and check from the **host**:

```bash
python3 scripts/k70.py verify-readback --stage wipe
```

Only after both checks pass, type **`FDL2>`**:

```text
reset
```

Recovery should perform the factory reset and boot to Android's welcome/setup screen. The first boot may take several minutes and USB may disappear during the reset. If the tablet stays black or loops, use the [recovery procedure](RECOVERY.md); keep the originals intact.

## 6. Finish Magisk and verify root after a reboot

Complete Android setup. Enable Developer options and USB debugging again, unlock the screen, and accept the computer's USB debugging authorization. Check “Always allow from this computer” if appropriate.

On the **host**:

```bash
adb -s "$SERIAL" install -r work/tools/Magisk-v30.7.apk
```

Open Magisk on the tablet and accept **“Requires additional setup”**. Let it complete and reboot. Reauthorize USB debugging if prompted.

On the **host**:

```bash
adb -s "$SERIAL" wait-for-device
adb -s "$SERIAL" shell 'getprop sys.boot_completed; getprop ro.boot.flash.locked; getprop ro.boot.vbmeta.device_state; getprop ro.boot.verifiedbootstate; getenforce'
adb -s "$SERIAL" shell su -c id
```

Allow the Shell superuser request in Magisk if one appears. Expected results, after Android has finished starting:

```text
1
0
unlocked
orange
Enforcing
uid=0(root) gid=0(root) groups=0(root) context=u:r:magisk:s0
```

Before additional setup, plain `su` was absent from PATH but `/debug_ramdisk/su -c id` worked. After setup and reboot, normal `su` resolved to `/system_ext/bin/su`. Do not disable SELinux to fix the PATH.

Keep your `work/stock/`, `work/tools/`, and preparation reports. Firmware updates and flashing other bootloader images can replace this boot chain; neither OTA survival nor other firmware versions have been tested.
