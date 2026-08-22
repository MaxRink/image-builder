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
import re
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

    def test_galaxy_token_is_serialized_and_not_leaked(self):
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

token_path = pathlib.Path(sys.argv[1])
observed_path = pathlib.Path(sys.argv[2])
with token_path.open(encoding="utf-8") as token_file:
    token_config = json.load(token_file)
observed_path.write_text(
    json.dumps(
        {
            "args": sys.argv[3:],
            "collections_path": os.environ.get("ANSIBLE_COLLECTIONS_PATH"),
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
            "ANSIBLE_GALAXY_COLLECTIONS_PATH": "/custom/collections",
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
                (
                    "set -euo pipefail; source ./hack/utils.sh; set -x; "
                    "ansible_galaxy_collection_install example.collection:1.0.0"
                ),
            ],
            cwd=CAPI_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )

        details = json.loads(observed.read_text(encoding="utf-8"))
        self.assertEqual({"token": token}, details["token_config"])
        self.assertEqual("/custom/collections", details["collections_path"])
        self.assertEqual(0o600, details["mode"])
        self.assertEqual("", details["token_env"])
        self.assertNotIn("--token", details["args"])
        self.assertNotIn(token, result.stdout + result.stderr)
        self.assertFalse(list((home / ".ansible").glob("image-builder-galaxy-token-*")))

    def test_make_exports_custom_collection_path_before_existing_path(self):
        marker = self.workdir / "make-expanded"
        custom_path = f"$(shell touch {marker})/custom/collections"
        existing_path = "/existing/collections:/usr/share/ansible/collections"
        environment = {
            **os.environ,
            "ANSIBLE_GALAXY_COLLECTIONS_PATH": custom_path,
            "ANSIBLE_COLLECTIONS_PATH": existing_path,
            "FLATCAR_VERSION": "test",
        }
        (self.workdir / "Makefile").write_text(
            f"include {CAPI_ROOT / 'Makefile'}\n"
            "print-collections-path:\n"
            '\t@printf "%s\\n" "$$ANSIBLE_COLLECTIONS_PATH"\n',
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "-s",
                "-f",
                str(self.workdir / "Makefile"),
                "print-collections-path",
            ],
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )

        self.assertFalse(marker.exists())
        self.assertEqual(f"{custom_path}:{existing_path}\n", result.stdout)

    def test_gce_scripts_preserve_galaxy_environment(self):
        expected_variables = {
            "ANSIBLE_COLLECTIONS_PATH",
            "ANSIBLE_GALAXY_COLLECTIONS_PATH",
            "ANSIBLE_GALAXY_IGNORE_CERTS",
            "ANSIBLE_GALAXY_NO_CACHE",
            "ANSIBLE_GALAXY_OFFLINE",
            "ANSIBLE_GALAXY_SERVER",
            "ANSIBLE_GALAXY_TIMEOUT",
            "ANSIBLE_GALAXY_TOKEN",
            "ANSIBLE_GALAXY_TOKEN_PATH",
        }

        for script_name in ("ci-gce.sh", "ci-gce-nightly.sh"):
            script = (CAPI_ROOT / "scripts" / script_name).read_text(encoding="utf-8")
            match = re.search(r'galaxy_env_whitelist="([^"]+)"', script)
            self.assertIsNotNone(match, script_name)
            self.assertTrue(
                expected_variables <= set(match.group(1).split(",")),
                script_name,
            )
            self.assertIn(
                'su --whitelist-environment="${galaxy_env_whitelist},',
                script,
            )
