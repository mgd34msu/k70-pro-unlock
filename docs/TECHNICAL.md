# Technical notes and evidence

## Scope of the verification

The original successful run used the saved build-specific preparation script, TomKing062's patcher, the pinned donor loaders, and interactive `spd_dump`. This repository turns those operations into reusable helpers. Offline integration against the original captures must reproduce the exact SPL and U-Boot bytes read back during the hardware test.

The tested device booted Android normally after the recovery wipe, ran Magisk 30.7, and returned UID 0 again after Magisk's additional setup and reboot. Full image readbacks were compared before every tested modified boot. SELinux remained enforcing.

This is a U-Boot lock-state bypass plus a persistent patched SPL. It does not recover a vendor signing key, obtain an official unlock token, or change secure boot efuses. The stored original lock data remained available for recovery.

## SPL: five downstream checks

The 4 MiB SPL capture contains a DHTB header at file offset 0, a payload beginning at `0x200`, and payload size `0xf7f0` at header offset `0x30`.

The following **file offsets** each begin a four-instruction check:

| File offset | Error code loaded on failure |
| --- | --- |
| `0xae10` | `0x1e` |
| `0xaf20` | `0x12` |
| `0xb060` | `0x1b` |
| `0xb094` | `0x1c` |
| `0xb0c4` | `0x1e` |

Each pattern is:

```asm
bl   verify_image      // forward call; target at file-relative 0xb150
cbz  w0, success       // word 0x34000060
mov  w0, error_code
bl   failure_handler
```

All four instructions at each of the five sites become `nop` (`0xd503201f`). This is the general pattern used by the [upstream Android 11+ SPL patcher](https://github.com/TomKing062/CVE-2022-38694_unlock_bootloader/blob/41d8c1ac2d54c6d04865e6a122c1d4fac27ed57f/gen_spl-unlock.c). The original run checked that its output differed only at those sites. Matching a fixed error code of `5` would miss this firmware.

The downstream patch alone is not the complete tested SPL image. The modified image is passed to [CVE-2022-38691_38692](https://github.com/TomKing062/CVE-2022-38691_38692/tree/ea1cd3159061cca7211a326ae8abecf784d50c9b) with the upstream `ums512.cfg`:

```text
anti-rollback minimum: 0 (upstream also preserves a higher image version)
execute address:      0x5700
g_n:                  0x2168
g_sig:                0x2268
save_to_mem usage:    0x30
saved LR locations:   0x3ce8, 0x3c68, 0x3c08, 0x3ca8, 0x3c98
```

The exploit certificate's key length is `0xdc40`; its modulus bytes match the working RAM FDL1 certificate. The SPL executable payload remains exactly the five-site NOP patch after packaging. The payload SHA256 is written into the DHTB header, and the rest of the original full boot partition after the generated package is preserved. The resulting full SHA256 must match the tested profile.

FDL1 is sent to `0x5500`; its payload entry after the `0x200` header is `0x5700`. The supplied FDL1 already embeds the exploit, so the separate `exec_addr` mechanism must be omitted.

## U-Boot: one branch

U-Boot's payload runs at `0x9f000000`. Its DHTB file header precedes the payload by `0x200` bytes. The lock function starts at payload offset `0x617b4`.

The patch is at **payload offset `0x61814`**, **file offset `0x61a14`**:

```asm
// original word 0xd2800001
mov x1, #0

// replacement word 0x1400000b
b   0x9f061840
```

It jumps to the function's existing unlocked-result block:

```asm
mov w0, #1
mov w21, w0
str w0, [x20, #0x8c8]
b   0x9f0617f8        // existing cleanup and return
```

The global lock-state address is `0x9f1228c8`. The host-side Unicorn check executes the function with stubbed allocation, zeroing, miscdata read, logging, and free calls. It verifies that the original function returns/stores `0`, while the patched function returns/stores `1` and still runs cleanup. This is a narrow control-flow check, not an emulation of the whole tablet or its security processor.

The U-Boot payload SHA256 is recomputed. The full 3 MiB output must match `68353cbd9cc219135300dd81aa1ccd6ad7cf8c4674502b6c4990a15afea53f3a`.

## Normal boot AVB versus fastboot verification

The successful patch retains the normal-boot verification calls and original `vbmeta`. Normal-boot verification also supplies the kernel's dm-verity command line and root-of-trust data; removing those calls wholesale can prevent Android from booting. The approach was informed by [UnisocBypass's UMS512 notes](https://github.com/TheGammaSqueeze/UnisocBypass/blob/1d046241ec2c0e96cf3c55c7e18e88e74acbe2da/docs/UBOOT_UNLOCK.md).

The fastboot flashing path is separate. Its saved log showed the patched screen's `UNLOCK` flag, followed by `sprd_fb_secure_vboot_verify` for `init_boot`, return code `3`, and a panic in `secure_avb_verify_image`. Both 8 MiB `init_boot` readbacks were still stock afterward. The BootROM write path installed Magisk successfully.

## Magisk and reset

The captured `init_boot` is an Android boot image v4 with no kernel and an LZ4-compressed generic ramdisk. Magisk's ARM64 tools were extracted from the digest-verified 30.7 APK and run on the same tablet. The patched ramdisk test returned `1`, meaning Magisk-patched, and the full image was 8 MiB.

The recovery request uses the standard 2048-byte bootloader-message region in `misc`:

- command, bytes `0:32`: `boot-recovery`, NUL padded;
- recovery arguments, bytes `64:832`: `recovery\n--wipe_data\n--reason=bootloader_unlock\n--locale=en_US\n`, NUL padded;
- bytes `2048:`: unchanged, preserving A/B and vendor metadata.

The original successful run verified the full request image after writing, reset, and reached Android's welcome screen. User setup and Magisk's additional setup were then completed. The final observed results were:

```text
Magisk: 30.7:MAGISK:R
su: /system_ext/bin/su
uid=0(root) gid=0(root) groups=0(root) context=u:r:magisk:s0
sys.boot_completed=1
ro.boot.flash.locked=0
ro.boot.vbmeta.device_state=unlocked
ro.boot.verifiedbootstate=orange
getenforce=Enforcing
```

## What is and is not covered

- BootROM read/write, the SPL/U-Boot patch bytes, both mirrored copies, the recovery wipe, and root after a reboot were hardware-verified.
- The repository helpers are tested offline against those captures; future changes need the same output-hash checks.
- Windows, macOS, other builds/regions, slot `b` as the starting active slot, OTA survival, custom ROMs, and full final-state stock restoration have not been hardware-tested here.
- Stock U-Boot restoration after the earlier failed experiment was hardware-tested. The recovery guide makes that narrower evidence explicit.

## Reproducing the offline checks

```bash
python3 -m unittest discover -s tests -v
python3 -O -m unittest discover -s tests -v
bash -n scripts/bootrom.sh
```

The tests verify refusal of unknown stock, incorrect sizes/hashes, mismatched second copies, reused capture destinations, and unmodified Magisk images. They also check that the wipe request preserves everything beyond the bootloader-message region. The checks remain active under Python optimization; firmware validation does not depend on `assert`.

With your own matching original captures and the pinned tools, `prepare` performs the full image reconstruction and lock-function emulation. During packaging, that operation reproduced both hardware-tested image hashes. The freshly built old flasher also matched the actual successful session's executable byte for byte (SHA256 `c7460757bf2442f93c9b5d8f0d4d939d3b98f72c0719566e9e631b87af108cab` on the original host); other compiler/toolchain builds can have different executable hashes while using the pinned source.
