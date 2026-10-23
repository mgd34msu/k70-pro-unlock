# Raemond K70 Pro unlock and root

A reproducible record of unlocking and rooting the **Raemond K70_PRO, UMS512 / T610, Android 16** tablet sold through Amazon Marketplace. The tested result is Magisk **30.7**, normal Android boot, and root that survives a reboot with SELinux enforcing.

```text
$ adb -s YOUR_TABLET_SERIAL shell su -c id
uid=0(root) gid=0(root) groups=0(root) context=u:r:magisk:s0

ro.boot.flash.locked=0
ro.boot.vbmeta.device_state=unlocked
ro.boot.verifiedbootstate=orange
sys.boot_completed=1
SELinux: Enforcing
```

**Start with the [step-by-step guide](docs/GUIDE.md).** Keep the [stock recovery procedure](docs/RECOVERY.md) available before changing anything. [Troubleshooting](docs/TROUBLESHOOTING.md) explains the failures you can skip.

## Supported hardware and firmware

| Item | Hardware-tested value |
| --- | --- |
| Brand / model | `raemond` / `K70_PRO` |
| Board / platform | `ums512_1h10` / `ums512` |
| Reported SoC / chip | T610 / `UMS512-AC` |
| Android | 16 / API 36 |
| Build | `K70_Pro_US_A16_20260912` |
| Fingerprint | `raemond/K70Pro_US/K70Pro:16/BP2A.250605.031.A3/2026091201:user/release-keys` |
| Storage / tested active slot | eMMC / `a` |
| Host | Linux x86-64 |
| Successful verification | October 22, 2026, America/Chicago; October 23 UTC |

**One physical tablet has been tested.** A similar Amazon listing, case, product name, or Unisoc chip does not establish compatibility. The scripts require the exact stock image sizes and SHA256 hashes in the [firmware profile](profiles/k70-pro-us-a16-20260912.json). A mismatch stops preparation; changing the profile to silence that check is not a port.

## What worked

1. Enter the actual USB BootROM with the tablet's physical buttons.
2. Use `spd_dump` at commit `f2fc779210d9e4b5ca1904c79a49cc5e114b58f3` with the checked UMS512 FDL1/FDL2 pair. **Omit `exec_addr 0x3ee8`.** FDL1 already contains its bypass.
3. Capture both original SPL copies, both U-Boot slots, both `init_boot` slots, `vbmeta`, and the device's own `misc`/`miscdata`.
4. NOP the five downstream image verification checks in this build's SPL, then apply TomKing062's persistent CVE-2022-38691/38692 patcher with `ums512.cfg`.
5. Patch one U-Boot instruction so its existing unlocked-result block executes. Recompute the SPL/U-Boot DHTB hashes.
6. Flash through the BootROM loader and compare full readbacks of **both** copies. The tested FDL2 mirrors the writes used here, including `_a` writes, onto the second copy.
7. Patch the tablet's own `init_boot` with Magisk on that same tablet. Write it through BootROM, then perform a recovery factory reset.
8. Complete Magisk's additional setup, reboot, and verify UID 0.

The successful workflow leaves the stock `vbmeta`, TrustOS, SML, kernel, and system partitions in place. The [technical notes](docs/TECHNICAL.md) explain the exact patches and evidence.

## Before you start

- **Expect a factory reset.** It erases apps, accounts, and local files. Back up personal data separately; the partition captures in this guide are not a backup of your photos or apps.
- Keep your own original images and recovery tools on the computer. Do not restore another tablet's `miscdata`, calibration data, or partition table.
- Keep the bootloader unlocked while modified images are installed. Do not run a relock command against this boot chain.
- Use one connected Unisoc USB device during BootROM work. The old flasher does not select a BootROM device using its Android ADB serial.
- Charge the tablet and use a dependable data cable. Release the buttons once the loader reaches `FDL2>`.

## Repository contents

| Path | Purpose |
| --- | --- |
| [`docs/GUIDE.md`](docs/GUIDE.md) | Ordered procedure with expected results and verification gates |
| [`docs/RECOVERY.md`](docs/RECOVERY.md) | Restore your original boot chain through BootROM |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | Known failure modes and the fixes actually used |
| [`docs/TECHNICAL.md`](docs/TECHNICAL.md) | Addresses, instruction changes, trust-chain details, and test evidence |
| [`tools.lock.json`](tools.lock.json) | Exact upstream revisions, asset URLs, sizes, and hashes |
| [`scripts/fetch-tools.py`](scripts/fetch-tools.py) | Download verified assets and build pinned upstream tools |
| [`scripts/k70.py`](scripts/k70.py) | Offline compatibility checks, image preparation, command printing, readback checks |
| [`scripts/patch-magisk.py`](scripts/patch-magisk.py) | Patch on the explicitly selected tablet; no flashing or rebooting |
| [`scripts/bootrom.sh`](scripts/bootrom.sh) | Open the tested interactive loader; no flash commands |
| [`tests/`](tests/) | Refusal, metadata preservation, and readback validation tests |

No stock firmware, prepatched firmware, serial numbers, personal device logs, unlock tokens, credentials, or third-party private keys are committed. Tool downloads, captures, and generated images stay under ignored `work/`. The scripts do not automatically flash anything: they print commands to review and paste at the `FDL2>` prompt.

## Credits and upstream sources

- [TomKing062/spreadtrum_flash](https://github.com/TomKing062/spreadtrum_flash): the USB dumper/flasher, building on [ilyakurdyukov/spreadtrum_flash](https://github.com/ilyakurdyukov/spreadtrum_flash).
- [TomKing062/CVE-2022-38691_38692](https://github.com/TomKing062/CVE-2022-38691_38692): persistent SPL/FDL signature bypass and UMS512 configuration.
- [TomKing062/CVE-2022-38694_unlock_bootloader](https://github.com/TomKing062/CVE-2022-38694_unlock_bootloader): the general SPL signature-check patching pattern and Unisoc research.
- [TheGammaSqueeze/UnisocBypass](https://github.com/TheGammaSqueeze/UnisocBypass/tree/1d046241ec2c0e96cf3c55c7e18e88e74acbe2da): the working FDL pair, UMS512 boot-chain analysis, and the distinction between U-Boot lock state and normal-boot AVB processing.
- [Magisk](https://github.com/topjohnwu/Magisk/releases/tag/v30.7) and its [installation documentation](https://topjohnwu.github.io/Magisk/install.html): root and on-device image patching.

This repository's original scripts and documentation are MIT licensed. Upstream projects, downloads, and firmware retain their respective licenses and rights; fetching a tool does not relicense it.
