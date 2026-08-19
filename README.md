# Recovery package rebuild

The `rebuild_ingenic.py` script preserves the stock Slot 1/A payloads and adds
Slot 2/B entries to the Ingenic package:

- `images/xImage` remains the stock Slot 1/A kernel; `images/xImage2` receives
  the NebulaOS Slot 2/B kernel.
- `images/rootfs.squashfs` remains the stock Slot 1/A rootfs;
  `images/rootfs2.squashfs` receives the NebulaOS Slot 2/B rootfs.
- `images/zero.bin` remains the stock RTOS; `images/zero2.bin` is a stock copy.
- `images/ota` is set to `ota:kernel2` followed by two LF bytes so the device
  selects Slot 2/B.
- The embedded `configs/x2000/x2000e_mmc0_lpddr2_linux.cfg` profile enables
  `ota`, `rtos`, `rtos2`, `kernel`, `kernel2`, `rootfs`, and `rootfs2`, and
  retains the stock full-MMC erase behavior.

The archive is rewritten while preserving all other entries.

Example:

```sh
python3 scripts/rebuild_ingenic.py \
  Ender-3_V3_KE_1.1.0.12.ingenic \
  rebuilt.ingenic \
  --root2 rootfs.squashfs \
  --kernel2 xImage
```

## GitHub Actions

The workflow is started manually from the **Actions** tab. It selects the
newest published NebulaOS release, including prereleases, and downloads these
assets from that same release:

- `xImage`
- `rootfs.squashfs`

The NebulaOS release `tag_name` is reused for the Recovery release tag. The
rebuilt file is named:

```text
Ender-3_V3_KE_1.1.0.12-<nebula-tag>.ingenic
```

The workflow uploads the file as both an Actions artifact and a GitHub Release
asset. Rerunning it for the same NebulaOS tag replaces the existing `.ingenic`
asset. If NebulaOS has no published release containing both required assets,
the workflow stops with an explanatory error.

Because the template is larger than GitHub's 100 MB regular-file limit, it is
tracked with Git LFS. Install Git LFS before committing the template:

```sh
git lfs install
git add .gitattributes Ender-3_V3_KE_1.1.0.12.ingenic
```
