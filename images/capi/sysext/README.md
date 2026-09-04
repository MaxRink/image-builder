# systemd-sysext image builds

This directory contains generic helpers for optional system extension images.
Existing CAPI image targets do not use this path yet. Future `*-sysext` targets
can build minimal base images that install only the `systemd-sysext` plumbing
and expect Kubernetes, containerd, CNI, or other payloads to be supplied as
extension images at bootstrap time. `ansible/node-sysext.yml` composes the same
roles as `ansible/node.yml` minus `containerd` and `kubernetes`, so the base
image still gets the common packages, kernel modules, sysctls, and guest agents
that a system extension cannot supply later.

Those future sysext image targets should use `packer/goss/goss-sysext.yaml`
instead of the normal node Goss suite. That test checks the extension
directories and `systemd-sysext` availability, and fails if Kubernetes,
containerd, or CNI payloads are baked into the base image.

For a raw image that preloads sysext images on disk but keeps them inactive,
pass `systemd_sysext_enable_service=false` through `ansible_user_vars` and stage
the `.raw` files under `/opt/extensions/<name>`, which is not a systemd-sysext
search path. The `systemd_sysext` role creates that staging directory alongside
the `/etc/extensions` and `/var/lib/extensions` search paths, following the
layout the `gpu` role already uses for the Flatcar NVIDIA runtime extension.

System extension images are limited to `/usr` and `/opt`. Configuration,
mutable state, service enablement, kernel/firmware content, and bootloader
changes must stay in the base image, bootstrap data, or a future
`systemd-confext` path.

Build a layer from a prepared rootfs:

```bash
images/capi/sysext/build-sysext-layer.sh \
  --name kubernetes \
  --version v1.34.0 \
  --rootfs /path/to/rootfs \
  --output-dir out/sysext \
  --os-id ubuntu \
  --os-version 24.04
```

The rootfs must contain only `usr/` and `opt/`. If
`usr/lib/extension-release.d/extension-release.<raw-image-basename>` is
missing, the helper creates one from the supplied OS, version, and architecture
fields. `--os-id` and `--os-version` are required and must match the target
host's `/usr/lib/os-release` `ID` and `VERSION_ID` (for example `ubuntu`/`24.04`
or `flatcar`/`4152.2.0`); systemd-sysext refuses to merge the image at runtime
otherwise. The metadata filename must match the sysext image basename, for
example `extension-release.kubernetes-v1.34.0-x86-64` for
`kubernetes-v1.34.0-x86-64.raw`.
