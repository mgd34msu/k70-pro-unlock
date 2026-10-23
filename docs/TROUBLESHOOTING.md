# Failures you can skip

These are observations from the tested K70 Pro, not claims about every Unisoc device.

| Symptom / tempting approach | What happened here | Working response |
| --- | --- | --- |
| `fastboot flashing unlock` | Unknown command | Use the documented BootROM + SPL + U-Boot procedure. |
| `fastboot oem unlock` or the common public-key token method | Vendor unlock verification failed, including with a correctly concatenated token | Do not spend time repeatedly signing the same token with unrelated keys. |
| `fastboot getvar unlocked` / `getvar all` | Blank values, even with the patched bootloader | Check the screen's lock flag and later Android properties. |
| `adb root` | Unavailable on this production build | Magisk supplies `su`; root adbd is not required. |
| Fetching boot images through fastboot / fastbootd | Unsupported | Read full partitions through the tested BootROM loader. |
| `adb reboot autodloader` | Native download mode worked for reads, but secure verification rejected modified images | Use the physical BootROM path for writes. Native mode presented `SPRD4:AutoD`; true BootROM presented `SPRD3`. |
| Newer `spd_dump` at `5da1992...` | Native mode worked, but the true BootROM handshake timed out | Pin `f2fc779210d9e4b5ca1904c79a49cc5e114b58f3`. |
| Adding `exec_addr 0x3ee8` to the supplied FDL1 | Conflicts with the bypass already embedded in FDL1 | Omit it. See [upstream issue 215](https://github.com/TomKing062/CVE-2022-38694_unlock_bootloader/issues/215). |
| `FDL2: incompatible partition` during startup | Appeared with the working donor loader before it proceeded | Require the expected eMMC partition table, successful reads, and `FDL2>` before continuing. Do not treat that line alone as proof of success or failure. |
| One timeout after FDL1 execution / before `DISABLE_TRANSCODE` | Appeared in the successful sessions | Let the tool continue to its next handshake; judge by the final prompt and verified reads. |
| Holding Power through transfer | Can reset the tablet while loaders run | Release Power after the 10-second reset combo; release Volume Down at `FDL2>`. |
| Generic UMS512 SPL patcher finds zero checks | A strict `mov w0,#5` pattern missed this build's five different error codes | Use the exact build-checked patch in this repository. |
| Changing only U-Boot while leaving stock SPL | A certificate-preserving “magic64” package still failed to boot on this build | Patch this tablet's own SPL with the persistent exploit and use the simple direct U-Boot change. |
| Fastboot reports unlocked but flashing patched `init_boot` disconnects USB | The bootloader panicked in `secure_avb_verify_image`, return code 3; readback was still stock | Flash the checked Magisk image through BootROM. |
| Recovery says Android cannot load / data may be corrupt after the lock-state change | Observed before the successful reset | Complete the documented recovery factory reset after installing Magisk. |
| Recovery `adb shell` aborts while setting SELinux context | Recovery adbd could not start a shell | `adb reboot bootloader` worked; use BootROM for partition work. |
| `su: inaccessible or not found` but `magiskd` is running | Additional setup had not installed the usual PATH entry yet | Use `/debug_ramdisk/su -c id` to check, then finish Magisk setup and reboot. |
| ADB says `unauthorized` after the wipe or reboot | The tablet needed to authorize the host again | Unlock the display and approve USB debugging. |
| A write to `_a` changes `_b` | The donor FDL2 mirrors the writes used in this procedure | Back up and verify both copies; never rely on the other slot as an untouched fallback. |

## Missing or mismatched files

The helpers stop on a wrong size/hash, unexpected source revision, changed instruction pattern, reused output directory, or incomplete readback. Preserve the originals, keep previous captures, and correct the actual mismatch. Do not remove the checks to force an image through.

The newer dumper trimmed some DHTB images during earlier investigation. The tested older version returned the complete partition sizes using the documented `read_part` commands. A hash for a trimmed payload is not interchangeable with the full partition hash.

## No USB connection after a bad boot

Use the physical reset/BootROM combo in [recovery](RECOVERY.md). A black screen does not establish that BootROM is unavailable. This route successfully recovered the failed U-Boot experiment.

If the host still sees no attachment, check the cable, port, and power state before changing tools or images. `1782:4d00` appeared for both native download mode and BootROM, so VID/PID alone did not distinguish them; the working flasher's `SPRD3` handshake did.
