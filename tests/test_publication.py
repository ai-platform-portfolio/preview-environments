"""Publication safety checks using temporary Git and a fake GitHub API."""

import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="publication-test-")
        self.addCleanup(self.directory.cleanup)
        self.repo = Path(self.directory.name)
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Publication fixture")
        (self.repo / "migrations").mkdir()
        (self.repo / "migrations/atlas.sum").write_text("fixture checksum\n")
        (self.repo / "deploy").mkdir()
        (self.repo / "deploy/values.yaml").write_text((ROOT / "deploy/values.yaml").read_text())
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.sha = self.git("rev-parse", "HEAD")
        self.checksum = hashlib.sha256((self.repo / "migrations/atlas.sum").read_bytes()).hexdigest()
        bin_dir = self.repo / "bin"
        bin_dir.mkdir()
        gh = bin_dir / "gh"
        gh.write_text("#!/bin/sh\nprintf '%s\\n' \"$FAKE_GITHUB_RESPONSE\"\n")
        gh.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "SOURCE_SHA": self.sha,
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_REF": "refs/pull/42/merge",
            "GITHUB_REPOSITORY": "org/app",
            "PR_NUMBER": "42",
            "FAKE_GITHUB_RESPONSE": json.dumps({"state": "open", "head": {
                "sha": self.sha, "repo": {"full_name": "org/app"},
            }}),
            "FRONTEND_IMAGE": "localacrk8s.azurecr.io/portfolio/frontend:commit-" + self.sha,
            "BACKEND_IMAGE": "localacrk8s.azurecr.io/portfolio/backend:commit-" + self.sha,
            "FRONTEND_REVISION": self.sha,
            "BACKEND_REVISION": self.sha,
            "MIGRATION_REVISION": self.sha,
            "FRONTEND_DIGEST": "sha256:" + "a" * 64,
            "BACKEND_DIGEST": "sha256:" + "b" * 64,
            "MIGRATION_CHECKSUM": self.checksum,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_NUMBER": "12",
            "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_OUTPUT": str(self.repo / "outputs"),
            "RUNNER_TEMP": str(self.repo),
        }

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def run_script(self, name, success=True, **overrides):
        result = subprocess.run(
            ["python3" if name.endswith(".py") else "bash", str(ROOT / "scripts" / name)], cwd=self.repo,
            env={**self.env, **overrides}, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)

    def test_fork_and_non_main_publication_are_rejected_but_builds_allowed(self):
        fork = json.dumps({"state": "open", "head": {
            "sha": self.sha, "repo": {"full_name": "another/app"},
        }})
        self.run_script("check-publication-source.sh", False, FAKE_GITHUB_RESPONSE=fork)
        self.run_script("check-publication-source.sh", FAKE_GITHUB_RESPONSE=fork, PUBLISH="false")
        self.run_script("check-publication-source.sh", False,
                        GITHUB_EVENT_NAME="workflow_dispatch", GITHUB_REF="refs/heads/feature")
        self.run_script("check-publication-source.sh", GITHUB_EVENT_NAME="workflow_dispatch",
                        GITHUB_REF="refs/heads/feature", PUBLISH="false")

    def release(self, **overrides):
        self.run_script("write-artifact-record.sh", **overrides)
        self.run_script("write-release-values.py", **overrides)
        outputs = dict(line.split("=", 1) for line in (self.repo / "outputs").read_text().splitlines())
        return yaml.safe_load((self.repo / "release-values.yaml").read_text()), outputs

    def test_complete_values_preserve_app_intent_and_replace_artifact_pins(self):
        values, outputs = self.release()
        base = yaml.safe_load((ROOT / "deploy/values.yaml").read_text())
        self.assertEqual(values["components"]["api"]["port"], base["components"]["api"]["port"])
        self.assertEqual(values["components"]["api"]["database"], "messages")
        self.assertEqual(values["databases"]["messages"]["migration"]["tag"], self.sha)
        self.assertEqual(values["components"]["web"]["image"], "localacrk8s.azurecr.io/portfolio/frontend@sha256:" + "a" * 64)
        self.assertEqual(values["name"], values["namespace"])
        self.assertTrue(values["hostname"].startswith(values["name"] + "."))
        self.assertEqual(outputs["destination"], "oci://localacrk8s.azurecr.io/releases/org/app/pr-42")
        self.assertEqual(outputs["version"], "0.12.2-g" + self.sha)
        self.assertEqual(values["platform"]["atlas"]["rolePlanRepository"], outputs["role-repository"])
        self.assertTrue(values["platform"]["tests"]["playwright"]["enabled"])
        self.assertEqual(values["platform"]["release"]["expectedRevision"], self.sha)
        self.assertEqual(values["platform"]["release"]["check"]["repository"], "org/app")
        self.assertTrue(outputs["role-repository"].endswith("-roles"))
        self.assertEqual(yaml.safe_load((self.repo / "deploy/values.yaml").read_text()), base)

    def test_release_isolation_and_ordering(self):
        one, first = self.release()
        two, second = self.release(PR_NUMBER="43")
        other, third = self.release(GITHUB_REPOSITORY="different/app")
        main, fourth = self.release(GITHUB_EVENT_NAME="push", GITHUB_REF="refs/heads/main", PR_NUMBER="")
        self.assertEqual(len({v["name"] for v in (one, two, other, main)}), 4)
        self.assertEqual(len({v["destination"] for v in (first, second, third, fourth)}), 4)
        self.assertEqual(first["role-repository"], second["role-repository"])
        self.assertEqual(first["role-repository"], fourth["role-repository"])
        self.assertNotEqual(first["role-repository"], third["role-repository"])
        self.assertEqual(main["platform"]["release"]["expectedRevision"], self.sha)
        self.assertEqual(main["platform"]["release"]["check"]["repository"], "org/app")
        unusual, _ = self.release(GITHUB_REPOSITORY="org/___")
        self.assertTrue(unusual["name"].startswith("app-"))
        _, newer = self.release(GITHUB_RUN_NUMBER="13", GITHUB_RUN_ATTEMPT="1")
        _, retry = self.release(GITHUB_RUN_NUMBER="12", GITHUB_RUN_ATTEMPT="3")
        key = lambda version: tuple(int(v) for v in version.split("-", 1)[0].split("."))
        self.assertGreater(key(newer["version"]), key(retry["version"]))
        self.assertGreater(key(retry["version"]), key(first["version"]))

    def test_release_rejects_mismatched_source_migration_and_invalid_identity(self):
        self.release()
        path = self.repo / "artifacts.json"
        record = json.loads(path.read_text())
        for field in ("source", "migrations"):
            bad = json.loads(json.dumps(record))
            bad[field]["revision" if field == "source" else "tag"] = "f" * 40
            path.write_text(json.dumps(bad))
            self.run_script("write-release-values.py", False)
        path.write_text(json.dumps(record))
        for overrides in ({"PR_NUMBER": "../42"}, {"GITHUB_RUN_NUMBER": "bad"}, {"GITHUB_RUN_ATTEMPT": "0"}):
            self.run_script("write-release-values.py", False, **overrides)

    def test_pinned_chart_packages_and_renders_complete_release(self):
        values, _ = self.release()
        chart = Path(os.environ.get("APPLICATION_CHART", ROOT.parent / "application-helm-chart")).resolve()
        helm = os.environ.get("HELM_BIN", "helm")
        package_dir = self.repo / "package"
        shutil.copytree(chart, package_dir, ignore=shutil.ignore_patterns(".git", ".github"))
        metadata = yaml.safe_load((package_dir / "Chart.yaml").read_text())
        metadata.update(version="0.12.2-g" + self.sha, appVersion=self.sha)
        (package_dir / "Chart.yaml").write_text(yaml.safe_dump(metadata))
        shutil.copy(self.repo / "release-values.yaml", package_dir / "release-values.yaml")
        before = subprocess.check_output([helm, "template", "preview", str(package_dir), "-f",
                                          str(self.repo / "release-values.yaml")], text=True)
        subprocess.run([helm, "package", str(package_dir), "--destination", str(self.repo),
                        "--version", "0.12.2-g" + self.sha, "--app-version", self.sha], check=True, capture_output=True)
        package = next(self.repo.glob("application-*.tgz"))
        subprocess.run(["tar", "-xzf", str(package), "-C", str(self.repo)], check=True)
        after = subprocess.check_output([helm, "template", "preview", str(self.repo / "application"),
                                         "-f", str(self.repo / "application/release-values.yaml")], text=True)
        self.assertEqual(before, after)
        resources = list(yaml.safe_load_all(after))
        self.assertTrue(any(v and v["kind"] == "AtlasMigration" for v in resources))
        roles = next(v for v in resources if v and v["kind"] == "AtlasSchema")
        self.assertEqual(roles["spec"]["cloud"]["repo"], values["platform"]["atlas"]["rolePlanRepository"])
        self.assertTrue(any(v and v["kind"] == "Deployment" for v in resources))
        browser = next(v for v in resources if v and v["kind"] == "TestWorkflow")
        self.assertEqual(browser["spec"]["content"]["git"]["revision"], self.sha)
        self.assertEqual(browser["spec"]["content"]["git"]["uri"], "https://github.com/org/app.git")
        self.assertTrue(all(not v or v.get("metadata", {}).get("name") != "preview-poc" for v in resources))

    def test_current_pr_and_main(self):
        self.run_script("check-publication-source.sh")
        self.run_script("check-publication-source.sh", GITHUB_EVENT_NAME="push",
                        GITHUB_REF="refs/heads/main", FAKE_GITHUB_RESPONSE=self.sha)

    def test_stale_closed_and_malformed_pr(self):
        for response in [
            {"state": "open", "head": {"sha": "f" * 40}},
            {"state": "closed", "head": {"sha": self.sha}},
            {},
        ]:
            with self.subTest(response=response):
                self.run_script("check-publication-source.sh", False,
                                FAKE_GITHUB_RESPONSE=json.dumps(response))
        self.run_script("check-publication-source.sh", False, PR_NUMBER="bad")

    def test_checkout_mismatch_and_advanced_main(self):
        self.run_script("check-publication-source.sh", False, SOURCE_SHA="f" * 40)
        self.run_script("check-publication-source.sh", False, GITHUB_EVENT_NAME="push",
                        GITHUB_REF="refs/heads/main", FAKE_GITHUB_RESPONSE="f" * 40)

    def test_matching_artifact_record(self):
        self.run_script("write-artifact-record.sh")
        record = json.loads((self.repo / "artifacts.json").read_text())
        self.assertEqual(record["source"]["revision"], self.sha)
        self.assertEqual(record["images"]["frontend"]["reference"], "localacrk8s.azurecr.io/portfolio/frontend@sha256:" + "a" * 64)
        self.assertEqual(record["images"]["backend"]["reference"], "localacrk8s.azurecr.io/portfolio/backend@sha256:" + "b" * 64)
        self.assertEqual(record["migrations"]["tag"], self.sha)
        self.assertEqual(record["migrations"]["atlasSumSha256"], self.checksum)
        self.assertEqual(record["workflow"], {"runId": "123", "attempt": "2"})

    def test_incomplete_or_mixed_artifacts_are_rejected(self):
        for key, value in [
            ("FRONTEND_REVISION", "f" * 40), ("BACKEND_REVISION", ""),
            ("MIGRATION_REVISION", "f" * 40), ("FRONTEND_IMAGE", ""),
            ("BACKEND_IMAGE", ""), ("FRONTEND_DIGEST", ""),
            ("BACKEND_DIGEST", "sha256:bad"), ("MIGRATION_CHECKSUM", "f" * 64),
        ]:
            with self.subTest(key=key):
                self.run_script("write-artifact-record.sh", False, **{key: value})
                self.assertFalse((self.repo / "artifacts.json").exists())


if __name__ == "__main__":
    unittest.main()
