# systemd-sysext image builds

This directory contains generic helpers for optional system extension images.
Existing CAPI image targets do not use this path. The `*-sysext` targets build
base images that enable `systemd-sysext.service` and expect Kubernetes,
containerd, CNI, or other payloads to be supplied as extension images at
bootstrap time.

System extension images are limited to `/usr` and `/opt`. Configuration,
mutable state, service enablement, kernel/firmware content, and bootloader
changes must stay in the base image, bootstrap data, or a future
`systemd-confext` path.

Build a layer from a prepared rootfs:

```bash
make build-sysext-kubernetes \
  SYSEXT_LAYER_ROOTFS=/path/to/rootfs \
  SYSEXT_VERSION=v1.34.0 \
  SYSEXT_OUTPUT_DIR=out/sysext
```

The rootfs must contain only `usr/` and `opt/`. If
`usr/lib/extension-release.d/extension-release.<name>` is missing, the helper
creates one from the supplied OS, version, and architecture fields.
