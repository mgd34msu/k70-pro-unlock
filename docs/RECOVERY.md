# Restore the original boot chain

Use your own full original captures from `work/stock/`. This restores the partitions modified by the procedure; it is not a complete factory firmware package, does not restore wiped personal data, and does not replace device-specific provisioning.

The successful session demonstrated recovery from a nonbooting U-Boot experiment: the original U-Boot was restored, both 3 MiB readbacks matched exactly, and Android booted with verified boot green. Full restoration of the final modified SPL + U-Boot + Magisk combination has not been physically tested. The restore command plan is checked offline against the saved originals.

## Enter the immutable BootROM

On the host, from the repository:

```bash
python3 scripts/k70.py check-stock
python3 scripts/k70.py commands --stage restore > work/restore.commands
cat work/restore.commands
bash scripts/bootrom.sh
```

Keep USB connected. Hold **Volume Down + Power for 10 seconds**, release **Power**, and keep holding Volume Down until the loader reaches `FDL2>`. Then release Volume Down. Alternatively, power off, unplug, hold Volume Down alone, and reconnect USB.

This enters BootROM independently of the installed Android or U-Boot. It is the physical recovery route that worked after a black-screen boot test. Do not hold Power through FDL transfer.

## Restore and compare

Paste `work/restore.commands` into `FDL2>`. The command plan writes these original images in order:

1. `init_boot_a.img` through `init_boot_a`.
2. `uboot_a.img` through `uboot_a`.
3. `splloader.img` through `splloader`.

With the exact tested FDL2, these writes mirror to the respective second copies. The plan reads all six full images back into `work/readback-restore/`. It does not repartition the disk, restore `miscdata`, or erase storage.

Wait until every read completes. In another host terminal:

```bash
python3 scripts/k70.py verify-readback --stage restore
```

Every readback must match the corresponding original. If only one copy changed, stop rather than assuming the mirroring behavior is the same with your loader. If a read is short or interrupted, do not count it as verification.

After verification, type at `FDL2>`:

```text
reset
```

Returning from an unlocked to a stock locked boot state may require another recovery factory reset because the encryption state changed. You can prepare and verify the same standard wipe request described in [guide step 5](GUIDE.md#5-install-magisk-through-bootrom-and-request-the-factory-reset), using a fresh `--readback` directory if needed.

**Do not issue a fastboot relock command while any modified SPL, U-Boot, or `init_boot` image remains installed.** Restore the matching original images as a set. Do not substitute a firmware image merely because another seller also calls its tablet “K70 Pro.”

## Repeating a readback

The command generator refuses to reuse a nonempty readback directory so stale files cannot pass for a fresh read. Keep previous captures and choose a new destination:

```bash
python3 scripts/k70.py commands --stage restore --readback work/readback-restore-2
```

After running those printed commands at `FDL2>`:

```bash
python3 scripts/k70.py verify-readback --stage restore --readback work/readback-restore-2
```
