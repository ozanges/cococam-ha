"""Reserve the next unused Home Assistant image version and expose it after publication."""

import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CONFIG = Path("cococam/config.yaml")
VERSION = re.compile(r'^version: "(\d+)\.(\d+)\.(\d+)"$', re.MULTILINE)
MANIFEST_TYPES = (
    "application/vnd.oci.image.index.v1+json, "
    "application/vnd.docker.distribution.manifest.list.v2+json, "
    "application/vnd.oci.image.manifest.v1+json, "
    "application/vnd.docker.distribution.manifest.v2+json"
)


def next_version(image):
    major, minor, patch = map(int, VERSION.search(CONFIG.read_text()).groups())
    repository = image.removeprefix("ghcr.io/")
    if repository == image:
        raise ValueError("Expected a GHCR image")
    query = urlencode({"service": "ghcr.io", "scope": f"repository:{repository}:pull"})
    with urlopen(f"https://ghcr.io/token?{query}", timeout=20) as result:
        token = json.load(result)["token"]
    for candidate in range(patch + 1, patch + 100):
        version = f"{major}.{minor}.{candidate}"
        request = Request(
            f"https://ghcr.io/v2/{repository}/manifests/{version}",
            headers={"Authorization": f"Bearer {token}", "Accept": MANIFEST_TYPES},
            method="HEAD",
        )
        try:
            with urlopen(request, timeout=20):
                pass
        except HTTPError as error:
            if error.code == 404:
                return version
            raise
    raise RuntimeError("No unused patch tag found")


def update_manifest(version):
    contents = CONFIG.read_text()
    old_version = tuple(map(int, VERSION.search(contents).groups()))
    if tuple(map(int, version.split("."))) <= old_version:
        raise ValueError("Expected a version newer than the current manifest")
    CONFIG.write_text(VERSION.sub(f'version: "{version}"', contents, count=1))
    changelog = CONFIG.with_name("CHANGELOG.md")
    revision = os.environ["SOURCE_SHA"]
    repo = os.environ["GITHUB_REPOSITORY"]
    changelog.write_text(
        f"# {version}\n\n"
        f"- Publication automatique de l’image. [Code source de cette version]"
        f"(https://github.com/{repo}/commit/{revision}).\n\n"
        + changelog.read_text()
    )


if __name__ == "__main__":
    if sys.argv[1] == "plan":
        print(next_version(os.environ["IMAGE"]))
    elif sys.argv[1] == "publish":
        update_manifest(sys.argv[2])
    else:
        raise ValueError("Unknown release command")
