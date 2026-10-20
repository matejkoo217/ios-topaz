#!/usr/bin/env python3
"""Preflight for fuxiPkg: check the firmware matches the board file and the
compiled device tree before EDK II spends minutes on a build that cannot boot.

Modelled on UniXNU-sheng's scripts/check-sheng.py, which compares the firmware
memory map against the compiled DTB. That check exists for a reason: fuxiPkg was
copied from shengPkg, so a stale sheng address is exactly the failure mode to
catch here.

Run by `unixnu build firmware` from the build tree root. Paths are resolved
relative to this repository when possible.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ERRORS: list[str] = []
NOTES: list[str] = []


def repo_root() -> Path:
    """Find the device repository.

    The driver runs preflight from inside the build tree (out/<board>/tree),
    where board.toml does not exist, so walk up until the repository is found.
    """
    override = os.environ.get("UNIXNU_DEVICE_DIR") or os.environ.get("UNIXNU_DEVICE")
    if override and (Path(override) / "board.toml").is_file():
        return Path(override).resolve()
    # The tree lives under <umbrella>/out/<board>/tree, and the device
    # repository is a sibling of the umbrella, so also look at each ancestor's
    # children for a directory that carries board.toml.
    for parent in Path(__file__).resolve().parents:
        if (parent / "board.toml").is_file():
            return parent
        for candidate in sorted(parent.glob("unixnu-*/board.toml")):
            return candidate.parent.resolve()
    raise SystemExit("check-fuxi: cannot locate the device repository (board.toml)")


def find_uefi(root: Path) -> Path | None:
    for candidate in (
        os.environ.get("UNIXNU_UEFI"),
        os.environ.get("UEFI_DIR"),
    ):
        if candidate and Path(candidate).is_dir():
            return Path(candidate).resolve()
    for candidate in (
        root.parent / "uefi-fuxi",
        root / "uefi-fuxi",
        root.parent / "uefi-sheng",
        Path("uefi-fuxi"),
    ):
        if candidate.is_dir():
            return candidate.resolve()
    return None


def main() -> int:
    root = repo_root()
    board = tomllib.loads((root / "board.toml").read_text())

    uefi = find_uefi(root)
    if uefi is None:
        print("check-fuxi: uefi-fuxi checkout not found (set UNIXNU_UEFI)", file=sys.stderr)
        return 2

    # --- firmware configuration: base/size are compiled into BootShim --------
    config_path = uefi / "Resources/Configs" / f"{board['firmware']['config']}.toml"
    if not config_path.is_file():
        ERRORS.append(f"missing firmware config: {config_path}")
        config = {}
    else:
        config = tomllib.loads(config_path.read_text())

    fd = config.get("uefi_fd", {})
    base, size = fd.get("base"), fd.get("size")
    if base is None or size is None:
        ERRORS.append("fuxi.toml has no [uefi_fd] base/size")
    else:
        # fuxi: 0xa7000000 + 0x300000 sits in the ABL's free DDR below the
        # kernel's own conventions; the value must match the DSC/FDF output.
        if not (0x80000000 <= base < 0x100000000):
            ERRORS.append(f"uefi_fd.base {base:#x} is outside the first DRAM bank")
        if size % 0x1000:
            ERRORS.append(f"uefi_fd.size {size:#x} is not page aligned")

    # --- device tree the boot image will carry ------------------------------
    dtb = root / "Resources/DTBs/fuxi.dtb"
    if not dtb.is_file():
        ERRORS.append(f"missing {dtb}; compile scripts/fuxi.dts first")
    else:
        # fdtget takes the file first: `fdtget <file> <node> <property>`.
        def fdtget(*positional: str) -> str:
            out = subprocess.run(["fdtget", str(dtb), *positional], capture_output=True, text=True)
            return out.stdout.strip() if out.returncode == 0 else ""

        def fdt_list(node: str) -> str:
            out = subprocess.run(["fdtget", "-l", str(dtb), node], capture_output=True, text=True)
            return out.stdout.strip() if out.returncode == 0 else ""

        model = fdtget("/", "model")
        compatible = fdtget("/", "compatible")
        if "fuxi" not in model and "fuxi" not in compatible:
            ERRORS.append(f"DTB does not describe fuxi: model={model!r} compatible={compatible!r}")
        # The splash node is injected by the driver ([[bootimg.dtb_node]]), so
        # the source tree must NOT already contain it.
        if "splash_region" in fdt_list("/reserved-memory"):
            ERRORS.append("DTB already contains splash_region; bootimg's fdtput would fail with FDT_ERR_EXISTS")
        if not fdtget("/memory@80000000", "reg"):
            NOTES.append("no /memory@80000000 node in the DTB (UEFI gets memory from the FD map)")

    # --- firmware memory map: the sheng inheritance lives here --------------
    memmap = uefi / "Platforms/Xiaomi/fuxiPkg/Library/MemoryMapLib/MemoryMapLib.c"
    if not memmap.is_file():
        ERRORS.append(f"missing {memmap}")
    else:
        text = memmap.read_text()
        rows = re.findall(r'\{"([^"]+)"\s*,\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)', text)
        display = [r for r in rows if r[0].replace("_", " ").lower() == "display reserved"]
        if not display:
            ERRORS.append('MemoryMapLib has no "Display Reserved" entry; SimpleFbDxe finds the framebuffer by that name')
        else:
            address, length = int(display[0][1], 16), int(display[0][2], 16)
            # The ABL splash window, verified from fuxi's own reserved-memory.
            if address != 0xB8000000 or length < 0x2B00000:
                ERRORS.append(f"Display Reserved is {address:#x}+{length:#x}, fuxi needs 0xb8000000+0x2b00000")
        if len(rows) > 128:
            ERRORS.append(f"{len(rows)} memory-map regions, the library allows 128")

    # --- panel geometry: the other sheng leftover ---------------------------
    dsc = uefi / "Platforms/Xiaomi/fuxiPkg/fuxi.dsc"
    if dsc.is_file():
        dsc_text = dsc.read_text()
        for pcd, want in (("PcdFrameBufferWidth", 1080), ("PcdFrameBufferHeight", 2400)):
            match = re.search(rf"{pcd}\|(\d+)", dsc_text)
            if not match:
                ERRORS.append(f"{pcd} not set in fuxi.dsc")
            elif int(match.group(1)) != want:
                ERRORS.append(f"{pcd} is {match.group(1)}, fuxi's panel is {want}")
    else:
        ERRORS.append(f"missing {dsc}")

    for note in NOTES:
        print(f"check-fuxi: note: {note}")
    if ERRORS:
        for error in ERRORS:
            print(f"check-fuxi: FAIL: {error}", file=sys.stderr)
        return 1
    print(f"check-fuxi: OK ({uefi.name}, fd {base:#x}+{size:#x}, panel 1080x2400)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
