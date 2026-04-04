"""Tests for the ready scan engine."""

import json
import os
import tempfile
import pytest
from src.validators import (
    run_scan,
    evaluate_checkpoint,
    Status,
    Severity,
    CheckType,
)


@pytest.fixture
def sample_repo(tmp_path):
    """Create a minimal sample repo for testing."""
    # README
    (tmp_path / "README.md").write_text("# My Service\nA sample service.")

    # License
    (tmp_path / "LICENSE").write_text("MIT License")

    # CI
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: CI\non: [push]")

    # Tests
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("def test_placeholder(): pass")

    # Source with health endpoint
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text(
        'from flask import Flask\napp = Flask(__name__)\n\n@app.route("/health")\ndef health():\n    return "ok"\n'
    )

    # Dependencies
    (tmp_path / "requirements.txt").write_text("flask==3.0.0\n")

    # .gitignore
    (tmp_path / ".gitignore").write_text("__pycache__/\n*.pyc\n")

    return tmp_path


@pytest.fixture
def definitions_path(tmp_path):
    """Write minimal definitions for testing."""
    defs = {
        "version": "1.0",
        "checkpoints": [
            {
                "id": "gen-001",
                "title": "README exists",
                "severity": "red",
                "type": "code",
                "verification": {"method": "file_exists", "pattern": "README.md"},
            },
            {
                "id": "gen-002",
                "title": "License file exists",
                "severity": "yellow",
                "type": "code",
                "verification": {"method": "glob", "pattern": "LICENSE*", "min_matches": 1},
            },
            {
                "id": "gen-003",
                "title": "CI configured",
                "severity": "red",
                "type": "code",
                "verification": {
                    "method": "glob",
                    "pattern": ".github/workflows/*.yml",
                    "min_matches": 1,
                },
            },
            {
                "id": "gen-004",
                "title": "Tests exist",
                "severity": "red",
                "type": "code",
                "verification": {
                    "method": "glob",
                    "pattern": "tests/**",
                    "min_matches": 1,
                },
            },
            {
                "id": "ops-001",
                "title": "Health endpoint",
                "severity": "red",
                "type": "code",
                "verification": {
                    "method": "grep",
                    "pattern": "(health|healthz|healthcheck)",
                    "target": "**/*.py",
                    "min_matches": 1,
                },
                "applicable_tags": ["web-api"],
            },
            {
                "id": "sec-001",
                "title": "No secrets in code",
                "severity": "red",
                "type": "code",
                "verification": {
                    "method": "grep",
                    "pattern": "AKIA[0-9A-Z]{16}",
                    "target": "**/*.py",
                    "min_matches": 0,
                },
            },
            {
                "id": "ext-001",
                "title": "Monitoring dashboard",
                "severity": "red",
                "type": "external",
                "verification": {
                    "method": "external_attestation",
                    "attestation_key": "monitoring_dashboard",
                },
                "applicable_tags": ["web-api"],
            },
        ],
    }
    path = tmp_path / "defs.json"
    path.write_text(json.dumps(defs, indent=2))
    return str(path)


@pytest.fixture
def empty_evidence(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps({"version": "1.0", "attestations": []}))
    return str(path)


@pytest.fixture
def empty_exceptions(tmp_path):
    path = tmp_path / "exceptions.json"
    path.write_text(json.dumps({"version": "1.0", "exceptions": []}))
    return str(path)


class TestFullScan:
    def test_passing_scan(self, sample_repo, definitions_path, empty_evidence, empty_exceptions):
        result = run_scan(
            repo_root=str(sample_repo),
            definitions_path=definitions_path,
            evidence_path=empty_evidence,
            exceptions_path=empty_exceptions,
            service_tags=["web-api"],
        )
        # README, License, CI, Tests, Health, No-secrets should pass
        # External monitoring will fail (no attestation)
        assert result.passing >= 5
        assert result.failing_red >= 1  # ext-001 monitoring

    def test_readiness_percentage(self, sample_repo, definitions_path, empty_evidence, empty_exceptions):
        result = run_scan(
            repo_root=str(sample_repo),
            definitions_path=definitions_path,
            evidence_path=empty_evidence,
            exceptions_path=empty_exceptions,
            service_tags=["web-api"],
        )
        assert 0 <= result.readiness_pct <= 100

    def test_tag_filtering(self, sample_repo, definitions_path, empty_evidence, empty_exceptions):
        """Checkpoints with non-matching tags should be skipped."""
        result = run_scan(
            repo_root=str(sample_repo),
            definitions_path=definitions_path,
            evidence_path=empty_evidence,
            exceptions_path=empty_exceptions,
            service_tags=["cli-tool"],  # Not a web-api
        )
        # ops-001 and ext-001 should be skipped
        skipped = [r for r in result.results if r.status == Status.SKIP]
        assert len(skipped) >= 2


class TestIndividualChecks:
    def test_file_exists_pass(self, sample_repo):
        cp = {
            "id": "test-001",
            "title": "README exists",
            "severity": "red",
            "type": "code",
            "verification": {"method": "file_exists", "pattern": "README.md"},
        }
        result = evaluate_checkpoint(cp, str(sample_repo), {}, {})
        assert result.status == Status.PASS

    def test_file_exists_fail(self, sample_repo):
        cp = {
            "id": "test-002",
            "title": "CHANGELOG exists",
            "severity": "yellow",
            "type": "code",
            "verification": {"method": "file_exists", "pattern": "CHANGELOG.md"},
        }
        result = evaluate_checkpoint(cp, str(sample_repo), {}, {})
        assert result.status == Status.FAIL

    def test_grep_pass(self, sample_repo):
        cp = {
            "id": "test-003",
            "title": "Health endpoint",
            "severity": "red",
            "type": "code",
            "verification": {
                "method": "grep",
                "pattern": "health",
                "target": "**/*.py",
                "min_matches": 1,
            },
        }
        result = evaluate_checkpoint(cp, str(sample_repo), {}, {})
        assert result.status == Status.PASS
        assert len(result.evidence) > 0

    def test_secrets_detection(self, sample_repo):
        """min_matches=0 means finding matches is a FAIL."""
        # Add a file with a fake AWS key
        secrets_file = sample_repo / "src" / "config.py"
        secrets_file.write_text('AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n')

        cp = {
            "id": "sec-001",
            "title": "No secrets",
            "severity": "red",
            "type": "code",
            "verification": {
                "method": "grep",
                "pattern": "AKIA[0-9A-Z]{16}",
                "target": "**/*.py",
                "min_matches": 0,
            },
        }
        result = evaluate_checkpoint(cp, str(sample_repo), {}, {})
        assert result.status == Status.FAIL

    def test_external_attestation_missing(self):
        cp = {
            "id": "ext-001",
            "title": "Monitoring",
            "severity": "red",
            "type": "external",
            "verification": {
                "method": "external_attestation",
                "attestation_key": "monitoring_dashboard",
            },
        }
        evidence = {"version": "1.0", "attestations": []}
        result = evaluate_checkpoint(cp, "/tmp", evidence, {})
        assert result.status == Status.FAIL

    def test_external_attestation_present(self):
        cp = {
            "id": "ext-001",
            "title": "Monitoring",
            "severity": "red",
            "type": "external",
            "verification": {
                "method": "external_attestation",
                "attestation_key": "monitoring_dashboard",
            },
        }
        evidence = {
            "version": "1.0",
            "attestations": [
                {
                    "checkpoint_id": "monitoring_dashboard",
                    "attested_by": "jwalters",
                    "attested_date": "2026-03-01",
                    "evidence_link": "https://dashboard.example.com/my-service",
                    "expires": "2026-12-01",
                }
            ],
        }
        result = evaluate_checkpoint(cp, "/tmp", evidence, {})
        assert result.status == Status.PASS


class TestExceptions:
    def test_active_exception(self, sample_repo):
        cp = {
            "id": "gen-099",
            "title": "Missing thing",
            "severity": "red",
            "type": "code",
            "verification": {"method": "file_exists", "pattern": "DOES_NOT_EXIST.md"},
        }
        exceptions = {
            "version": "1.0",
            "exceptions": [
                {
                    "checkpoint_id": "gen-099",
                    "justification": "Not applicable to this service",
                    "accepted_by": "jwalters",
                    "accepted_date": "2026-01-01",
                    "expires": "2027-01-01",
                }
            ],
        }
        result = evaluate_checkpoint(cp, str(sample_repo), {}, exceptions)
        assert result.status == Status.EXCEPTION

    def test_expired_exception(self, sample_repo):
        cp = {
            "id": "gen-099",
            "title": "Missing thing",
            "severity": "red",
            "type": "code",
            "verification": {"method": "file_exists", "pattern": "DOES_NOT_EXIST.md"},
        }
        exceptions = {
            "version": "1.0",
            "exceptions": [
                {
                    "checkpoint_id": "gen-099",
                    "justification": "Temporary gap",
                    "accepted_by": "jwalters",
                    "accepted_date": "2024-01-01",
                    "expires": "2024-06-01",
                }
            ],
        }
        result = evaluate_checkpoint(cp, str(sample_repo), {}, exceptions)
        assert result.status == Status.EXPIRED_EXCEPTION


class TestScanResult:
    def test_is_ready_true(self, sample_repo, definitions_path, empty_evidence, empty_exceptions):
        """A repo with no red failures should be ready (if no external checks apply)."""
        result = run_scan(
            repo_root=str(sample_repo),
            definitions_path=definitions_path,
            evidence_path=empty_evidence,
            exceptions_path=empty_exceptions,
            service_tags=["cli-tool"],  # Skips web-api checks
        )
        assert result.is_ready is True

    def test_to_dict(self, sample_repo, definitions_path, empty_evidence, empty_exceptions):
        result = run_scan(
            repo_root=str(sample_repo),
            definitions_path=definitions_path,
            evidence_path=empty_evidence,
            exceptions_path=empty_exceptions,
        )
        d = result.to_dict()
        assert "summary" in d
        assert "results" in d
        assert isinstance(d["results"], list)


class TestTagFiltering:
    """Tag filtering is critical UX — these tests cover the None vs [] distinction."""

    def test_empty_tags_skips_service_checks(self, sample_repo, definitions_path, empty_evidence, empty_exceptions):
        """service_tags=[] means 'I declared my tags, none match' — skip service-specific checks."""
        result = run_scan(
            repo_root=str(sample_repo),
            definitions_path=definitions_path,
            evidence_path=empty_evidence,
            exceptions_path=empty_exceptions,
            service_tags=[],
        )
        skipped = [r for r in result.results if r.status == Status.SKIP]
        skipped_ids = {r.checkpoint_id for r in skipped}
        # ops-001 (web-api) and ext-001 (web-api) should be skipped
        assert "ops-001" in skipped_ids
        assert "ext-001" in skipped_ids

    def test_none_tags_runs_everything(self, sample_repo, definitions_path, empty_evidence, empty_exceptions):
        """service_tags=None means 'not configured' — run all checks regardless of tags."""
        result = run_scan(
            repo_root=str(sample_repo),
            definitions_path=definitions_path,
            evidence_path=empty_evidence,
            exceptions_path=empty_exceptions,
            service_tags=None,
        )
        skipped = [r for r in result.results if r.status == Status.SKIP]
        assert len(skipped) == 0  # Nothing skipped when tags not configured

    def test_matching_tag_runs_check(self, sample_repo, definitions_path, empty_evidence, empty_exceptions):
        """service_tags=['web-api'] should run checks tagged with 'web-api'."""
        result = run_scan(
            repo_root=str(sample_repo),
            definitions_path=definitions_path,
            evidence_path=empty_evidence,
            exceptions_path=empty_exceptions,
            service_tags=["web-api"],
        )
        # ops-001 should NOT be skipped (it applies to web-api)
        ops_001 = [r for r in result.results if r.checkpoint_id == "ops-001"][0]
        assert ops_001.status != Status.SKIP

    def test_universal_checks_always_run(self, sample_repo, definitions_path, empty_evidence, empty_exceptions):
        """Checks with applicable_tags=[] should run regardless of service tags."""
        result = run_scan(
            repo_root=str(sample_repo),
            definitions_path=definitions_path,
            evidence_path=empty_evidence,
            exceptions_path=empty_exceptions,
            service_tags=["some-random-tag"],
        )
        # gen-001 (README) has no applicable_tags — should never be skipped
        gen_001 = [r for r in result.results if r.checkpoint_id == "gen-001"][0]
        assert gen_001.status != Status.SKIP
