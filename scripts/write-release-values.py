"""Map this application's validated artifact record to central-chart values."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

import yaml


def azure_json(*arguments):
    return json.loads(subprocess.run(['az', *arguments, '--only-show-errors', '-o', 'json'],
                                     capture_output=True, text=True, check=True, timeout=60).stdout)


def preview_readers(pr):
    intent = Path("deploy/preview-readers.yaml")
    agents = (yaml.safe_load(intent.read_text()) or {}).get(pr, []) if intent.is_file() else []
    if not agents:
        return {}
    if not isinstance(agents, list) or any(not isinstance(agent, str) or
            not re.fullmatch(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?", agent) for agent in agents):
        raise ValueError("Preview readers must name approved Foundry agents")
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    project = urlsplit(endpoint)
    if (project.scheme != "https" or not project.hostname
            or not project.hostname.endswith(".services.ai.azure.com")
            or project.netloc != project.hostname or project.query or project.fragment
            or not re.fullmatch(r"/api/projects/[a-zA-Z0-9-]+", project.path)):
        raise ValueError("Preview readers require the platform Foundry project endpoint")
    def foundry(path):
        return azure_json("rest", "--url", path + "?api-version=v1", "--resource", "https://ai.azure.com")

    readers = {}
    for agent in agents:
        url = f"{endpoint}/agents/{agent}"
        detail = foundry(url)
        rule, = detail["agent_endpoint"]["version_selector"]["version_selection_rules"]
        version = rule["agent_version"]
        if (rule["type"] != "FixedRatio" or rule["traffic_percentage"] != 100
                or not re.fullmatch(r"[1-9][0-9]*", version)):
            raise ValueError("Preview reader must be an agent on a fixed serving version")
        deployed = foundry(f"{url}/versions/{version}")
        if deployed.get("name") != agent or deployed.get("version") != version:
            raise ValueError("Foundry returned a different runtime version")
        principal = deployed["instance_identity"]["principal_id"]
        if not re.fullmatch(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", principal):
            raise ValueError("Foundry returned an invalid runtime principal")
        readers[agent] = principal
    cluster = azure_json("aks", "show", "--resource-group", os.environ["AKS_RESOURCE_GROUP"],
                         "--name", os.environ["AKS_NAME"], "--query", "id")
    return {"aksArmId": cluster, "workloadReaders": readers}


def write_release():
    record = json.loads(Path("artifacts.json").read_text())
    repository = os.environ["GITHUB_REPOSITORY"]
    revision = os.environ["SOURCE_SHA"]
    run = os.environ["GITHUB_RUN_NUMBER"]
    attempt = os.environ["GITHUB_RUN_ATTEMPT"]
    pr = os.environ.get("PR_NUMBER", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Expected an owner/repository identity")
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or record["source"] != {
        "repository": repository, "revision": revision,
    }:
        raise ValueError("Artifact source does not match this publication")
    if any(not re.fullmatch(r"[1-9][0-9]*", value) for value in (run, attempt)):
        raise ValueError("Positive workflow run number and attempt required")
    if os.environ["GITHUB_EVENT_NAME"] == "pull_request":
        if not re.fullmatch(r"[1-9][0-9]{0,9}", pr):
            raise ValueError("Positive PR number required")
        scope = f"pr-{pr}"
    elif os.environ["GITHUB_REF"] == "refs/heads/main":
        scope = "main"
    else:
        raise ValueError("Only PR and main releases are supported")

    values = yaml.safe_load(Path("deploy/values.yaml").read_text())
    for component, image in (("web", "frontend"), ("api", "backend")):
        reference = record["images"][image]["reference"]
        if not re.fullmatch(r"localacrk8s\.azurecr\.io/[a-z0-9/_.-]+@sha256:[0-9a-f]{64}", reference):
            raise ValueError("Expected a digest-pinned application image in ACR")
        values["components"][component]["image"] = reference
    migration = record["migrations"]
    if migration["tag"] != revision:
        raise ValueError("Migration must match the selected source SHA")
    values["databases"]["messages"]["migration"] = {
        "repository": migration["repository"], "tag": revision,
    }

    # GitHub identity, rather than a manually maintained preview name, owns isolation.
    canonical = repository.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", canonical.split("/")[1]).strip("-")[:28].rstrip("-") or "app"
    suffix = hashlib.sha256(canonical.encode()).hexdigest()[:12]
    name = f"{slug}-{suffix}-{scope}"
    domain = values["hostname"].partition(".")[2]
    if not domain:
        raise ValueError("Application hostname must include its deployment domain")
    values.update(name=name, namespace=name, hostname=f"{name}.{domain}")
    # Plan history belongs to the application repository, shared across its previews.
    role_repository = f"{slug}-{suffix}-roles"
    values.setdefault("platform", {}).setdefault("atlas", {})["rolePlanRepository"] = role_repository
    if scope.startswith("pr-"):
        azure = preview_readers(pr)
        if azure:
            values["platform"].setdefault("azure", {}).update(azure)

    version = f"0.{run}.{attempt}-g{revision}"
    destination = f"oci://localacrk8s.azurecr.io/releases/{canonical}/{scope}"
    output = Path(os.environ["RUNNER_TEMP"]) / "release-values.yaml"
    output.write_text(yaml.safe_dump(values, sort_keys=False))
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as stream:
        stream.write(f"values={output}\ndestination={destination}\nversion={version}\nrole-repository={role_repository}\n")


if __name__ == "__main__":
    write_release()
