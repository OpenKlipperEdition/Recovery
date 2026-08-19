# Recovery package rebuild

The `rebuild_ingenic.py` script preserves the stock Slot 1/A payloads and adds
Slot 2/B entries to the Ingenic package:

- `images/xImage` remains the stock kernel; `images/xImage2` receives kernel2.
- `images/rootfs.squashfs` remains the stock rootfs; `images/rootfs2.squashfs`
  receives root2.
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

The GitHub Actions workflow is started manually. It resolves the latest
latest published NebulaOS release (including prereleases), downloads its
`xImage` and `rootfs.squashfs` assets, and uses that release's `tag_name` for
the rebuilt package's GitHub Release. It then
rebuilds the package as
`Ender-3_V3_KE_1.1.0.12-<nebula-tag>.ingenic`, uploads it as an Actions
artifact, and creates or updates that GitHub Release. Rerunning the workflow for
the same NebulaOS tag replaces the `.ingenic` release asset.

Because the template is larger than GitHub's 100 MB regular-file limit, it is
tracked with Git LFS. Install Git LFS before committing the template:

```sh
git lfs install
git add .gitattributes Ender-3_V3_KE_1.1.0.12.ingenic
```
