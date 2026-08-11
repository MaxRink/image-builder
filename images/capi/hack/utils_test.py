#!/usr/bin/env python3

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

import json
import os
import pathlib
import shutil
import subprocess
import unittest


CAPI_ROOT = pathlib.Path(__file__).resolve().parents[1]


class UtilsTests(unittest.TestCase):
    def setUp(self):
        self.workdir = CAPI_ROOT / f".utils-test-{os.getpid()}"
        if self.workdir.exists():
            shutil.rmtree(self.workdir)
        self.workdir.mkdir()
        self.addCleanup(shutil.rmtree, self.workdir, ignore_errors=True)

    def test_galaxy_token_is_yaml_mapping_and_not_leaked(self):
        fake_bin = self.workdir / "bin"
        fake_bin.mkdir()
        home = self.workdir / "home"
        home.mkdir()
        observed = self.workdir / "observed.json"
        fake_galaxy = fake_bin / "ansible-galaxy"
        fake_galaxy.write_text(
            """#!/usr/bin/env bash
set -euo pipefail
python3 - "$ANSIBLE_GALAXY_TOKEN_PATH" "$TEST_UTILS_WORKDIR/observed.json" "$@" <<'PY'
import json
import os
import pathlib
import stat
import sys

import yaml

token_path = pathlib.Path(sys.argv[1])
observed_path = pathlib.Path(sys.argv[2])
with token_path.open(encoding="utf-8") as token_file:
    token_config = yaml.safe_load(token_file)
observed_path.write_text(
    json.dumps(
        {
            "args": sys.argv[3:],
            "mode": stat.S_IMODE(token_path.stat().st_mode),
            "token_config": token_config,
            "token_env": os.environ.get("ANSIBLE_GALAXY_TOKEN"),
        }
    ),
    encoding="utf-8",
)
PY
""",
            encoding="utf-8",
        )
        fake_galaxy.chmod(0o755)

        token = "s3cr3t: # not a comment\nline with 'quotes' and \\\\slash"
        environment = {
            **os.environ,
            "ANSIBLE_GALAXY_SERVER": "https://galaxy.example.test",
            "ANSIBLE_GALAXY_TOKEN": token,
            "HOME": str(home),
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            "TEST_UTILS_WORKDIR": str(self.workdir),
        }
        environment.pop("ANSIBLE_GALAXY_TOKEN_PATH", None)

        result = subprocess.run(
            [
                "bash",
                "-c",
                "set -euo pipefail; source ./hack/utils.sh; set -x; "
                "ansible_galaxy_collection_install example.collection:1.0.0",
            ],
            cwd=CAPI_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )

        details = json.loads(observed.read_text(encoding="utf-8"))
        self.assertEqual({"token": token}, details["token_config"])
        self.assertEqual(0o600, details["mode"])
        self.assertEqual("", details["token_env"])
        self.assertNotIn("--token", details["args"])
        self.assertNotIn(token, result.stdout + result.stderr)
        self.assertFalse(list((home / ".ansible").glob("image-builder-galaxy-token-*")))

    def test_make_exports_custom_collection_path_before_existing_path(self):
        custom_path = r"/custom/collections\with\$literal"
        existing_path = "/existing/collections:/usr/share/ansible/collections"
        environment = {
            **os.environ,
            "ANSIBLE_GALAXY_COLLECTIONS_PATH": custom_path,
            "ANSIBLE_COLLECTIONS_PATH": existing_path,
            "FLATCAR_VERSION": "test",
        }

        result = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "-s",
                "-C",
                str(CAPI_ROOT),
                "--eval",
                "print-collections-path:\n"
                '\t@printf "%s\\n" "$$ANSIBLE_COLLECTIONS_PATH"\n',
                "print-collections-path",
            ],
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )

        self.assertEqual(f"{custom_path}:{existing_path}\n", result.stdout)
