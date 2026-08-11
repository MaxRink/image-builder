#!/bin/bash

# Copyright 2021 The Kubernetes Authors.
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

################################################################################
# usage: ci-gce-nightly.sh
# This program build all images for capi gce for the nightly build
################################################################################

set -o errexit
set -o nounset
set -o pipefail

[[ -n ${DEBUG:-} ]] && set -o xtrace

CAPI_ROOT=$(dirname "${BASH_SOURCE[0]}")/..
cd "${CAPI_ROOT}" || exit 1

# Verify the required Environment Variables are present.
: "${GCP_PROJECT:?Environment variable empty or not defined.}"

# to list and check if have the properly access to the service account
gcloud auth list

# assume we are running in the CI environment as root
# Add a user for ansible to work properly
groupadd -r packer && useradd -m -s /bin/bash -r -g packer packer
chown -R packer:packer /home/prow/go/src/sigs.k8s.io/image-builder
# use the packer user to run the build
galaxy_env_whitelist="ANSIBLE_GALAXY_SERVER,ANSIBLE_GALAXY_TOKEN,ANSIBLE_GALAXY_TOKEN_PATH,ANSIBLE_GALAXY_IGNORE_CERTS,ANSIBLE_GALAXY_TIMEOUT,ANSIBLE_GALAXY_COLLECTIONS_PATH,ANSIBLE_GALAXY_NO_CACHE,ANSIBLE_GALAXY_OFFLINE,ANSIBLE_COLLECTIONS_PATH"
export GCP_PROJECT_ID="${GCP_PROJECT}"

# Build image for each available config
for f in packer/gce/ci/nightly/*.json
do
  # using PACKER_FLAGS=-force to overwrite the previous image and keep the same name
  export PACKER_VAR_FILES="${f}"
  export PACKER_FLAGS=-force
  su --whitelist-environment="${galaxy_env_whitelist},GCP_PROJECT_ID,PACKER_VAR_FILES,PACKER_FLAGS" \
    - packer -c "bash -c 'cd /home/prow/go/src/sigs.k8s.io/image-builder/images/capi && PATH=\$PATH:~packer/.local/bin:/home/prow/go/src/sigs.k8s.io/image-builder/images/capi/.local/bin make deps-gce build-gce-all'"
done

echo "Displaying the generated image information"
filter="name~cluster-api-ubuntu-*"
gcloud compute images list --project "$GCP_PROJECT" \
  --no-standard-images --filter="${filter}"

echo "Making images public to use in CI"
(gcloud compute images list --project "$GCP_PROJECT" --no-standard-images --filter="${filter}" --format="value(name[])" | \
awk '{print "gcloud compute images add-iam-policy-binding --project '"$GCP_PROJECT"' " $1 " --member='"'allAuthenticatedUsers'"' --role='"'roles/compute.imageUser'"' \n"}' | bash)
