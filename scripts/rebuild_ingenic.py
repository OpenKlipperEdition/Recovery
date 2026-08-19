#!/usr/bin/env python3
"""Add Slot 2/B payloads to an Ingenic ZIP package."""

from __future__ import annotations

import argparse
import copy
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path


STOCK_ROOTFS_ENTRY = "images/rootfs.squashfs"
STOCK_KERNEL_ENTRY = "images/xImage"
STOCK_RTOS_ENTRY = "images/zero.bin"
DUAL_SLOT_CONFIG_ENTRY = "configs/x2000/x2000e_mmc0_lpddr2_linux.cfg"
DEFAULT_OTA_ENTRY = "images/ota"
DEFAULT_ROOT2_ENTRY = "images/rootfs2.squashfs"
DEFAULT_KERNEL2_ENTRY = "images/xImage2"
DEFAULT_RTOS2_ENTRY = "images/zero2.bin"
SLOT2_OTA_MARKER = b"ota:kernel2\n\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild an .ingenic package with stock Slot 1/A payloads and "
            "new Slot 2/B payloads."
        )
    )
    parser.add_argument("input", type=Path, help="Source .ingenic package")
    parser.add_argument("output", type=Path, help="Rebuilt .ingenic package")
    parser.add_argument("--root2", required=True, type=Path, help="root2 image")
    parser.add_argument("--kernel2", required=True, type=Path, help="kernel2 image")
    parser.add_argument(
        "--ota-entry",
        default=DEFAULT_OTA_ENTRY,
        help=f"OTA marker archive entry (default: {DEFAULT_OTA_ENTRY})",
    )
    parser.add_argument(
        "--root2-entry",
        default=DEFAULT_ROOT2_ENTRY,
        help=f"Slot 2/B rootfs archive entry (default: {DEFAULT_ROOT2_ENTRY})",
    )
    parser.add_argument(
        "--kernel2-entry",
        default=DEFAULT_KERNEL2_ENTRY,
        help=f"Slot 2/B kernel archive entry (default: {DEFAULT_KERNEL2_ENTRY})",
    )
    parser.add_argument(
        "--rtos2-entry",
        default=DEFAULT_RTOS2_ENTRY,
        help=f"Slot 2/B RTOS archive entry (default: {DEFAULT_RTOS2_ENTRY})",
    )
    return parser.parse_args()


def require_file(path: Path, description: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"{description} does not exist: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"{description} is empty: {path}")


def copy_entry(
    source: zipfile.ZipFile,
    destination: zipfile.ZipFile,
    source_info: zipfile.ZipInfo,
    destination_info: zipfile.ZipInfo | None = None,
) -> None:
    """Copy one source entry without loading its entire contents into memory."""
    if destination_info is None:
        # ZipFile.open(..., "w") updates the ZipInfo it receives. Keep the
        # source archive's metadata untouched so later entries remain readable.
        destination_info = copy.copy(source_info)
    with source.open(source_info, "r") as source_stream, destination.open(
        destination_info, "w"
    ) as destination_stream:
        shutil.copyfileobj(source_stream, destination_stream, length=1024 * 1024)


def copy_file(destination: zipfile.ZipFile, source_path: Path, info: zipfile.ZipInfo) -> None:
    """Write a replacement file using the original entry's ZIP metadata."""
    with source_path.open("rb") as source_stream, destination.open(info, "w") as destination_stream:
        shutil.copyfileobj(source_stream, destination_stream, length=1024 * 1024)


def write_bytes(destination: zipfile.ZipFile, payload: bytes, info: zipfile.ZipInfo) -> None:
    """Write a small generated archive entry."""
    destination.writestr(info, payload)


def set_config_value(data: bytes, section: str, key: str, value: str) -> bytes:
    """Replace one INI-style value while preserving its original line ending."""
    lines = data.splitlines(keepends=True)
    current_section = ""
    section_header = f"[{section}]".encode()
    key_prefix = f"{key}=".encode()

    for index, line in enumerate(lines):
        content = line.rstrip(b"\r\n")
        if content.startswith(b"[") and content.endswith(b"]"):
            current_section = content.decode("ascii")
        elif current_section == section_header.decode("ascii") and content.startswith(key_prefix):
            line_ending = line[len(content) :]
            lines[index] = key_prefix + value.encode("utf-8") + line_ending
            return b"".join(lines)

    raise ValueError(f"Missing {key} in [{section}] of {DUAL_SLOT_CONFIG_ENTRY}")


def configure_dual_slot_profile(data: bytes) -> bytes:
    """Enable the reference package's dual-slot X2000E/MMC0 policy."""
    values = {
        ("mmc", "erase_all"): "1",
        ("mmc", "erase_list"): '"0x0,0x1fffff;0x300000,0xffffffff;"',
        ("mmc", "force_erase"): "2",
        ("policy1", "attribute"): DEFAULT_OTA_ENTRY,
        ("policy1", "enabled"): "1",
        ("policy4", "attribute"): STOCK_RTOS_ENTRY,
        ("policy4", "enabled"): "1",
        ("policy5", "attribute"): DEFAULT_RTOS2_ENTRY,
        ("policy5", "enabled"): "1",
        ("policy6", "attribute"): STOCK_KERNEL_ENTRY,
        ("policy6", "enabled"): "1",
        ("policy7", "attribute"): DEFAULT_KERNEL2_ENTRY,
        ("policy7", "enabled"): "1",
        ("policy8", "attribute"): STOCK_ROOTFS_ENTRY,
        ("policy8", "enabled"): "1",
        ("policy9", "attribute"): DEFAULT_ROOT2_ENTRY,
        ("policy9", "enabled"): "1",
    }
    for (section, key), value in values.items():
        data = set_config_value(data, section, key, value)
    return data


def renamed_info(template: zipfile.ZipInfo, filename: str) -> zipfile.ZipInfo:
    """Reuse ZIP metadata from a stock entry under a Slot 2/B name."""
    info = copy.copy(template)
    info.filename = filename
    info.orig_filename = filename
    return info


def rebuild(args: argparse.Namespace) -> None:
    require_file(args.input, "Input package")
    require_file(args.root2, "root2 image")
    require_file(args.kernel2, "kernel2 image")

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    replacements = {
        args.root2_entry: args.root2.resolve(),
        args.kernel2_entry: args.kernel2.resolve(),
    }

    temporary_name: str | None = None
    try:
        with zipfile.ZipFile(args.input, "r") as source:
            infos = {info.filename: info for info in source.infolist()}
            required_stock_entries = {
                STOCK_ROOTFS_ENTRY,
                STOCK_KERNEL_ENTRY,
                STOCK_RTOS_ENTRY,
                DUAL_SLOT_CONFIG_ENTRY,
            }
            missing = [entry for entry in required_stock_entries if entry not in infos]
            if missing:
                raise ValueError(
                    "Input package is missing required Slot 1/A entries: "
                    + ", ".join(missing)
                )
            configured_profile = configure_dual_slot_profile(
                source.read(DUAL_SLOT_CONFIG_ENTRY)
            )

            target_entries = set(replacements) | {args.rtos2_entry, args.ota_entry}
            if target_entries & required_stock_entries:
                raise ValueError("Slot 2/B entry names must differ from Slot 1/A entry names")

            with tempfile.NamedTemporaryFile(
                dir=output.parent,
                prefix=f".{output.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_name = temporary.name

            with zipfile.ZipFile(temporary_name, "w", allowZip64=True) as destination:
                for info in source.infolist():
                    if info.filename == DUAL_SLOT_CONFIG_ENTRY:
                        write_bytes(
                            destination,
                            configured_profile,
                            copy.copy(info),
                        )
                    elif info.filename not in target_entries:
                        copy_entry(source, destination, info)

                # Keep the appended Slot 2/B entry order used by the
                # reference package: ota, RTOS, kernel, rootfs.
                write_bytes(
                    destination,
                    SLOT2_OTA_MARKER,
                    renamed_info(infos[STOCK_KERNEL_ENTRY], args.ota_entry),
                )
                copy_entry(
                    source,
                    destination,
                    infos[STOCK_RTOS_ENTRY],
                    renamed_info(infos[STOCK_RTOS_ENTRY], args.rtos2_entry),
                )
                copy_file(
                    destination,
                    replacements[args.kernel2_entry],
                    renamed_info(infos[STOCK_KERNEL_ENTRY], args.kernel2_entry),
                )
                copy_file(
                    destination,
                    replacements[args.root2_entry],
                    renamed_info(infos[STOCK_ROOTFS_ENTRY], args.root2_entry),
                )

        os.replace(temporary_name, output)
        temporary_name = None

    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass

    with zipfile.ZipFile(output, "r") as rebuilt:
        expected_sizes = {
            args.root2_entry: args.root2.stat().st_size,
            args.kernel2_entry: args.kernel2.stat().st_size,
            args.rtos2_entry: infos[STOCK_RTOS_ENTRY].file_size,
            args.ota_entry: len(SLOT2_OTA_MARKER),
        }
        for entry, expected_size in expected_sizes.items():
            actual_size = rebuilt.getinfo(entry).file_size
            if actual_size != expected_size:
                raise ValueError(
                    f"Replacement failed for {entry}: "
                    f"expected {expected_size} bytes, found {actual_size}"
                )
        if rebuilt.read(args.ota_entry) != SLOT2_OTA_MARKER:
            raise ValueError(f"OTA marker is not set to Slot 2/B in {args.ota_entry}")
        if rebuilt.read(DUAL_SLOT_CONFIG_ENTRY) != configured_profile:
            raise ValueError(f"Dual-slot profile was not updated in {DUAL_SLOT_CONFIG_ENTRY}")

    print(f"Wrote {output} ({output.stat().st_size} bytes)")
    print(f"  {STOCK_ROOTFS_ENTRY} kept as Slot 1/A")
    print(f"  {STOCK_KERNEL_ENTRY} kept as Slot 1/A")
    print(f"  {STOCK_RTOS_ENTRY} kept as Slot 1/A")
    print(f"  {args.root2_entry} <- {args.root2} ({args.root2.stat().st_size} bytes)")
    print(f"  {args.kernel2_entry} <- {args.kernel2} ({args.kernel2.stat().st_size} bytes)")
    print(f"  {args.rtos2_entry} <- {STOCK_RTOS_ENTRY} (stock copy)")
    print(f"  {args.ota_entry} <- ota:kernel2 (Slot 2/B)")
    print(f"  {DUAL_SLOT_CONFIG_ENTRY} <- dual-slot Cloner policy")


def main() -> int:
    try:
        rebuild(parse_args())
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
