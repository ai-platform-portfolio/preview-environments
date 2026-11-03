"""Pin an environment to an already published, immutable application release."""

import json
import os
from pathlib import Path
import re

import yaml


def pin():
    target = os.environ["TARGET_ENVIRONMENT"]
    if target not in ("staging", "production"):
        raise ValueError("Expected staging or production")

    record = json.loads(Path("artifacts.json").read_text())
    repository = os.environ["GITHUB_REPOSITORY"].lower()
    source = record["source"]
    workflow = record["workflow"]
    release = record["release"]
    revision = source["revision"]
    if source["repository"].lower() != repository or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Published artifact belongs to another repository or has an invalid revision")
    if workflow["runId"] != os.environ["PUBLICATION_RUN_ID"]:
        raise ValueError("Artifact does not belong to the selected publication run")

    prefix = f"localacrk8s.azurecr.io/releases/{repository}/"
    match = re.fullmatch(
        re.escape(prefix) + r"(main|pr-[1-9][0-9]*)/application:(0\.[1-9][0-9]*\.[1-9][0-9]*-g([0-9a-f]{40}))",
        release["reference"],
    )
    if not match or match.group(3) != revision or not re.fullmatch(r"sha256:[0-9a-f]{64}", release["digest"]):
        raise ValueError("Release reference, digest and source revision do not agree")
    if any(not re.fullmatch(r"sha256:[0-9a-f]{64}", image["digest"]) or
           not image["reference"].endswith("@" + image["digest"])
           for image in record["images"].values()):
        raise ValueError("Application images must be digest pinned")
    if record["migrations"]["tag"] != revision:
        raise ValueError("Migration tag must match the selected source")

    pin_value = {"release": {"scope": match.group(1), "version": match.group(2), "sourceSha": revision}}
    path = Path("deploy/environments") / f"{target}.yaml"
    if target == "production":
        staging = yaml.safe_load(Path("deploy/environments/staging.yaml").read_text())
        if staging != pin_value:
            raise ValueError("Production must promote the exact release validated in staging")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Immutable publication selected for this environment.\n" + yaml.safe_dump(pin_value, sort_keys=False))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write(f"revision={revision}\nscope={match.group(1)}\nversion={match.group(2)}\n")


if __name__ == "__main__":
    pin()
