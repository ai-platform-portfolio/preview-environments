"""Publication safety checks using temporary Git and a fake GitHub API."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


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
            "FAKE_GITHUB_RESPONSE": json.dumps({"state": "open", "head": {"sha": self.sha}}),
            "FRONTEND_IMAGE": "registry/frontend:commit-" + self.sha,
            "BACKEND_IMAGE": "registry/backend:commit-" + self.sha,
            "FRONTEND_REVISION": self.sha,
            "BACKEND_REVISION": self.sha,
            "MIGRATION_REVISION": self.sha,
            "FRONTEND_DIGEST": "sha256:" + "a" * 64,
            "BACKEND_DIGEST": "sha256:" + "b" * 64,
            "MIGRATION_CHECKSUM": self.checksum,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "2",
        }

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def run_script(self, name, success=True, **overrides):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts" / name)], cwd=self.repo,
            env={**self.env, **overrides}, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)

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
        self.assertEqual(record["images"]["frontend"]["reference"], "registry/frontend@sha256:" + "a" * 64)
        self.assertEqual(record["images"]["backend"]["reference"], "registry/backend@sha256:" + "b" * 64)
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
