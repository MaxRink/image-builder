#!/usr/bin/env bash

# Copyright 2026 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for tool in mke2fs debugfs; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "SKIP: ${tool} is required for sysext layer helper smoke test" >&2
    exit 0
  fi
done

workdir="$(mktemp -d)"
cleanup() {
  rm -rf "${workdir}"
}
trap cleanup EXIT

rootfs="${workdir}/rootfs"
mkdir -p "${rootfs}/usr/share/sysext-test"
printf 'ok\n' > "${rootfs}/usr/share/sysext-test/payload"

raw="$("${script_dir}/build-sysext-layer.sh" \
  --name sysext-test \
  --version v1.2.3 \
  --rootfs "${rootfs}" \
  --output-dir "${workdir}/out" \
  --os-id ubuntu \
  --os-version 24.04 \
  --arch x86_64)"

# debugfs exits 0 whether or not the path resolves, so check that it actually
# printed an inode for the file.
assert_file_in_image() {
  local image="$1" path="$2"
  if ! debugfs -R "stat ${path}" "${image}" 2>/dev/null | grep -q '^Inode:'; then
    echo "missing expected path in sysext image: ${path}" >&2
    exit 1
  fi
}

assert_file_in_image "${raw}" \
  "/usr/lib/extension-release.d/extension-release.sysext-test-v1.2.3-x86-64"
assert_file_in_image "${raw}" "/usr/share/sysext-test/payload"

echo "sysext layer helper smoke test passed"
