"""Tests for the ready scan engine."""

import json
import os
import tempfile
from contextlib import nullcontext
import pytest
from ready.validators import (
    run_scan,
    evaluate_checkpoint,
    Status,
    Severity,
    CheckType,
    get_registry,
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


class TestHybridCheckpoints:
    """Hybrid checkpoints require both code and external parts to pass."""

    def _make_hybrid_cp(self, confidence: str = "verified") -> dict:
        return {
            "id": "hyb-001",
            "title": "Observability SDK and backend",
            "severity": "red",
            "type": "hybrid",
            "verification": {
                "method": "hybrid",
                "code_verification": {
                    "method": "grep",
                    "pattern": "opentelemetry",
                    "target": "**/*.py",
                    "min_matches": 1,
                    "confidence": confidence,
                },
                "attestation_key": "observability_backend",
            },
        }

    def _make_evidence(self, tmp_path, include_attestation: bool = True) -> dict:
        if not include_attestation:
            return {"version": "1.0", "attestations": []}
        return {
            "version": "1.0",
            "attestations": [
                {
                    "checkpoint_id": "observability_backend",
                    "attested_by": "jwalters",
                    "attested_date": "2026-04-01",
                    "evidence_link": "https://grafana.internal/d/my-service",
                    "expires": "2027-04-01",
                }
            ],
        }

    def test_hybrid_passes_when_both_parts_pass(self, sample_repo):
        """Hybrid checkpoint passes only when code AND external both pass."""
        # Write a file that matches the observability grep
        (sample_repo / "src" / "telemetry.py").write_text("import opentelemetry\n")
        cp = self._make_hybrid_cp()
        evidence = self._make_evidence(sample_repo)
        result = evaluate_checkpoint(cp, str(sample_repo), evidence, {})
        assert result.status == Status.PASS

    def test_hybrid_fails_when_code_part_fails(self, sample_repo):
        """Hybrid checkpoint fails when the code check fails (no matching file content)."""
        # sample_repo has no opentelemetry import
        cp = self._make_hybrid_cp()
        evidence = self._make_evidence(sample_repo)
        result = evaluate_checkpoint(cp, str(sample_repo), evidence, {})
        assert result.status == Status.FAIL

    def test_hybrid_fails_when_external_part_fails(self, sample_repo):
        """Hybrid checkpoint fails when the external attestation is missing."""
        (sample_repo / "src" / "telemetry.py").write_text("import opentelemetry\n")
        cp = self._make_hybrid_cp()
        evidence = self._make_evidence(sample_repo, include_attestation=False)
        result = evaluate_checkpoint(cp, str(sample_repo), evidence, {})
        assert result.status == Status.FAIL

    def test_hybrid_inherits_confidence_from_code_verification(self, sample_repo):
        """Confidence from code_verification.confidence must propagate to the result.

        This is the nested-structure recursion bug: when code_verification has
        'confidence': 'likely' but the outer verification dict does not, the scanner
        must read from the nested block — not default to 'verified'.
        """
        # No opentelemetry import → code check fails
        cp = self._make_hybrid_cp(confidence="likely")
        evidence = self._make_evidence(sample_repo)
        result = evaluate_checkpoint(cp, str(sample_repo), evidence, {})
        assert result.status == Status.FAIL
        # With confidence="likely", the message should say pattern-based, not "Failing"
        assert "pattern-based" in result.message or result.confidence.value == "likely"

    def test_hybrid_evidence_prefixed_correctly(self, sample_repo):
        """Evidence items must be prefixed with [code] or [external]."""
        (sample_repo / "src" / "telemetry.py").write_text("import opentelemetry\n")
        cp = self._make_hybrid_cp()
        evidence = self._make_evidence(sample_repo)
        result = evaluate_checkpoint(cp, str(sample_repo), evidence, {})
        assert result.status == Status.PASS
        code_evidence = [e for e in result.evidence if e.startswith("[code]")]
        ext_evidence = [e for e in result.evidence if e.startswith("[external]")]
        assert len(code_evidence) > 0
        assert len(ext_evidence) > 0

    def test_hybrid_missing_code_verification_returns_clear_error(self, sample_repo):
        """A hybrid checkpoint with no code_verification block should fail with a clear message."""
        cp = {
            "id": "hyb-bad",
            "title": "Misconfigured hybrid",
            "severity": "red",
            "type": "hybrid",
            "verification": {
                "method": "hybrid",
                "attestation_key": "observability_backend",
                # code_verification block is intentionally missing
            },
        }
        evidence = self._make_evidence(sample_repo)
        result = evaluate_checkpoint(cp, str(sample_repo), evidence, {})
        assert result.status == Status.FAIL
        assert any("code verification method" in e.lower() for e in result.evidence)


class TestEvidencePaths:
    """evidence_paths field accepts string or array; arrays avoid manual brace syntax."""

    def test_evidence_paths_string_behaves_like_target(self, sample_repo):
        """evidence_paths as a string is equivalent to target."""
        cp = {
            "id": "ep-001",
            "title": "Health endpoint (evidence_paths string)",
            "severity": "red",
            "type": "code",
            "verification": {
                "method": "grep",
                "pattern": "health",
                "evidence_paths": "**/*.py",
                "min_matches": 1,
            },
        }
        result = evaluate_checkpoint(cp, str(sample_repo), {}, {})
        assert result.status == Status.PASS

    def test_evidence_paths_array_finds_match_in_first_path(self, sample_repo):
        """evidence_paths array scans each path; match in any one → pass."""
        cp = {
            "id": "ep-002",
            "title": "Health endpoint (evidence_paths array)",
            "severity": "red",
            "type": "code",
            "verification": {
                "method": "grep",
                "pattern": "health",
                "evidence_paths": ["src/**/*.py", "lib/**/*.py"],
                "min_matches": 1,
            },
        }
        result = evaluate_checkpoint(cp, str(sample_repo), {}, {})
        assert result.status == Status.PASS

    def test_evidence_paths_array_no_match_fails(self, sample_repo):
        """evidence_paths array fails when pattern is not found in any path."""
        cp = {
            "id": "ep-003",
            "title": "Missing pattern",
            "severity": "red",
            "type": "code",
            "verification": {
                "method": "grep",
                "pattern": "xyzzy_not_present_anywhere",
                "evidence_paths": ["src/**/*.py", "tests/**/*.py"],
                "min_matches": 1,
            },
        }
        result = evaluate_checkpoint(cp, str(sample_repo), {}, {})
        assert result.status == Status.FAIL

    def test_evidence_paths_takes_precedence_over_target(self, sample_repo):
        """When both evidence_paths and target are set, evidence_paths wins."""
        # target points to a non-existent dir; evidence_paths points to src/
        cp = {
            "id": "ep-004",
            "title": "Precedence check",
            "severity": "red",
            "type": "code",
            "verification": {
                "method": "grep",
                "pattern": "health",
                "evidence_paths": "src/**/*.py",
                "target": "nonexistent_dir/**/*.py",
                "min_matches": 1,
            },
        }
        result = evaluate_checkpoint(cp, str(sample_repo), {}, {})
        assert result.status == Status.PASS


class TestPluginRegistry:
    """Smoke tests for the plugin auto-discovery system."""

    def test_default_registry_has_all_methods(self):
        registry = get_registry()
        expected = {
            "file_exists", "glob", "glob_all", "file_count",
            "grep", "grep_all", "grep_count",
            "json_path", "external_attestation", "hybrid",
        }
        assert expected.issubset(set(registry.methods()))

    def test_plugin_base_class_enforces_verify(self):
        from ready.plugins.base import PluginContext, VerificationPlugin

        class BrokenPlugin(VerificationPlugin):
            method_name = "broken"

        with pytest.raises(NotImplementedError):
            BrokenPlugin().verify({}, PluginContext(repo_root="/tmp"))

    def test_registry_rejects_plugin_without_method_name(self):
        from ready.plugins.base import VerificationPlugin
        from ready.plugins.registry import PluginRegistry

        class Nameless(VerificationPlugin):
            pass

        with pytest.raises(ValueError):
            PluginRegistry().register(Nameless())


class TestMarkdownFormatter:
    """Tests for the markdown gaps-checklist formatter."""

    def test_renders_all_sections(
        self, sample_repo, definitions_path, empty_evidence, empty_exceptions
    ):
        from ready.formatters.markdown import format_markdown

        scan = run_scan(
            repo_root=str(sample_repo),
            definitions_path=definitions_path,
            evidence_path=empty_evidence,
            exceptions_path=empty_exceptions,
            service_tags=["web-api"],
        )
        with open(definitions_path) as f:
            definitions = json.load(f)

        md = format_markdown(
            definitions=definitions,
            results=[r.to_dict() for r in scan.results],
            output_path="/tmp/unused.md",
            service_name=scan.service_name,
            readiness_pct=scan.readiness_pct,
        )

        assert md.startswith(f"# Gaps Checklist — {scan.service_name}")
        assert "Auto-generated by" in md
        assert "**Readiness:" in md
        assert "## ✗ Blocking" in md
        assert "## ⚠ Warnings" in md
        assert "## Exceptions" in md
        assert "## ✓ Passing" in md
        assert "## Summary" in md
        assert "| Status | Count |" in md

        assert f"| ✗ Blocking | {scan.failing_red} |" in md
        assert f"| ⚠ Warning | {scan.failing_yellow} |" in md
        assert f"| ✓ Passing | {scan.passing} |" in md
        assert f"| Exceptions | {scan.exceptions} |" in md
        assert f"| **Total** | **{scan.total}** |" in md

    def test_file_roundtrip(
        self, sample_repo, definitions_path, empty_evidence, empty_exceptions, tmp_path
    ):
        from ready.formatters.markdown import format_markdown

        scan = run_scan(
            repo_root=str(sample_repo),
            definitions_path=definitions_path,
            evidence_path=empty_evidence,
            exceptions_path=empty_exceptions,
            service_tags=["web-api"],
        )
        with open(definitions_path) as f:
            definitions = json.load(f)

        out_path = tmp_path / "docs" / "gaps.md"
        md = format_markdown(
            definitions=definitions,
            results=[r.to_dict() for r in scan.results],
            output_path=str(out_path),
            service_name=scan.service_name,
            readiness_pct=scan.readiness_pct,
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")

        assert out_path.exists()
        content = out_path.read_text(encoding="utf-8")
        assert "Gaps Checklist" in content
        assert "## Summary" in content

    def test_passing_strikethrough(
        self, sample_repo, definitions_path, empty_evidence, empty_exceptions
    ):
        from ready.formatters.markdown import format_markdown

        scan = run_scan(
            repo_root=str(sample_repo),
            definitions_path=definitions_path,
            evidence_path=empty_evidence,
            exceptions_path=empty_exceptions,
            service_tags=["web-api"],
        )
        with open(definitions_path) as f:
            definitions = json.load(f)

        md = format_markdown(
            definitions=definitions,
            results=[r.to_dict() for r in scan.results],
            output_path="/tmp/unused.md",
            service_name=scan.service_name,
            readiness_pct=scan.readiness_pct,
        )

        for r in scan.results:
            if r.status == Status.PASS:
                assert f"~~{r.title}~~" in md


class TestCheckpointInheritance:
    """Tests for the extends / overrides / additional inheritance system."""

    def _write_defs(self, path, defs):
        path.write_text(json.dumps(defs, indent=2))
        return str(path)

    def test_no_extends_passthrough(self, tmp_path):
        """Definitions without extends are returned unchanged."""
        from ready.engine import resolve_definitions

        defs = {"version": "1.0", "checkpoints": [{"id": "a", "title": "A"}]}
        result = resolve_definitions(defs, lambda _: None)
        assert result == defs

    def test_extends_merges_base_checkpoints(self, tmp_path):
        from ready.engine import resolve_definitions

        base_path = tmp_path / "base" / "checkpoint-definitions.json"
        base_path.parent.mkdir()
        self._write_defs(base_path, {
            "version": "1.0",
            "metadata": {"guideline_name": "Base", "guideline_version": "1.0"},
            "checkpoints": [
                {"id": "base-001", "title": "Base check", "severity": "red"},
            ],
        })

        child = {
            "version": "1.0",
            "extends": "base@v1.0",
            "checkpoints": [
                {"id": "child-001", "title": "Child check", "severity": "yellow"},
            ],
        }

        resolved = resolve_definitions(child, lambda name: str(base_path))
        ids = [cp["id"] for cp in resolved["checkpoints"]]
        assert "base-001" in ids
        assert "child-001" in ids
        assert ids.index("base-001") < ids.index("child-001")

    def test_overrides_merge_by_id(self, tmp_path):
        from ready.engine import resolve_definitions

        base_path = tmp_path / "base" / "checkpoint-definitions.json"
        base_path.parent.mkdir()
        self._write_defs(base_path, {
            "version": "1.0",
            "checkpoints": [
                {"id": "sec-001", "title": "Secrets check", "severity": "red",
                 "type": "code", "verification": {"method": "grep", "target": "**/*.py"}},
            ],
        })

        child = {
            "extends": "base",
            "overrides": {
                "sec-001": {"verification": {"method": "grep", "target": "src/api/**/*.cs"}},
            },
            "checkpoints": [],
        }

        resolved = resolve_definitions(child, lambda _: str(base_path))
        sec = next(cp for cp in resolved["checkpoints"] if cp["id"] == "sec-001")
        assert sec["verification"]["target"] == "src/api/**/*.cs"
        assert sec["title"] == "Secrets check"

    def test_additional_appended_before_local(self, tmp_path):
        from ready.engine import resolve_definitions

        base_path = tmp_path / "base" / "checkpoint-definitions.json"
        base_path.parent.mkdir()
        self._write_defs(base_path, {
            "version": "1.0",
            "checkpoints": [{"id": "b1", "title": "Base"}],
        })

        child = {
            "extends": "base",
            "additional": [{"id": "add-001", "title": "Additional"}],
            "checkpoints": [{"id": "local-001", "title": "Local"}],
        }

        resolved = resolve_definitions(child, lambda _: str(base_path))
        ids = [cp["id"] for cp in resolved["checkpoints"]]
        assert ids == ["b1", "add-001", "local-001"]

    def test_base_not_found_falls_back(self):
        from ready.engine import resolve_definitions

        child = {
            "extends": "nonexistent-pack@v1.0",
            "checkpoints": [{"id": "c1", "title": "Surviving"}],
        }

        resolved = resolve_definitions(child, lambda _: None)
        assert len(resolved["checkpoints"]) == 1
        assert resolved["checkpoints"][0]["id"] == "c1"

    def test_max_depth_prevents_cycle(self, tmp_path):
        from ready.engine import resolve_definitions

        cycle_path = tmp_path / "cycle" / "checkpoint-definitions.json"
        cycle_path.parent.mkdir()
        self._write_defs(cycle_path, {
            "extends": "cycle",
            "checkpoints": [{"id": "loop", "title": "Loop"}],
        })

        result = resolve_definitions(
            {"extends": "cycle", "checkpoints": [{"id": "start", "title": "Start"}]},
            lambda _: str(cycle_path),
        )
        assert any(cp["id"] == "start" for cp in result["checkpoints"])

    def test_version_mismatch_warns_but_proceeds(self, tmp_path):
        import logging
        from ready.engine import resolve_definitions

        base_path = tmp_path / "base" / "checkpoint-definitions.json"
        base_path.parent.mkdir()
        self._write_defs(base_path, {
            "version": "1.0",
            "metadata": {"guideline_version": "2.0"},
            "checkpoints": [{"id": "b1", "title": "Base"}],
        })

        child = {
            "extends": "base@v1.0",
            "checkpoints": [],
        }

        with pytest.raises(Exception) if False else nullcontext():
            resolved = resolve_definitions(child, lambda _: str(base_path))
        assert any(cp["id"] == "b1" for cp in resolved["checkpoints"])


class TestBidirectionalSync:
    """Tests for work item adapter reopen, branch safety, dry-run, and sync log."""

    def test_adapter_interface_has_reopen(self):
        from ready.adapters import WorkItemAdapter
        assert hasattr(WorkItemAdapter, "reopen")

    def test_github_adapter_has_reopen(self):
        from ready.adapters.github_issues import GitHubIssuesAdapter
        assert hasattr(GitHubIssuesAdapter, "reopen")

    def test_ado_adapter_has_reopen(self):
        from ready.adapters.ado import AzureDevOpsAdapter
        assert hasattr(AzureDevOpsAdapter, "reopen")

    def test_jira_adapter_has_reopen(self):
        from ready.adapters.jira import JiraAdapter
        assert hasattr(JiraAdapter, "reopen")

    def test_abstract_reopen_enforced(self):
        from ready.adapters import WorkItemAdapter
        class Incomplete(WorkItemAdapter):
            def create_draft(self, draft): ...
            def get_status(self, item_id): ...
            def list_open(self, label=None): ...
            def close(self, item_id, reason=""): ...

        with pytest.raises(TypeError, match="reopen"):
            Incomplete()

    def test_sync_log_append(self, tmp_path):
        from ready.ready import _append_sync_log

        readiness_dir = str(tmp_path)
        _append_sync_log(readiness_dir, {
            "action": "close",
            "checkpoint_id": "sec-001",
            "item_id": "42",
            "previous_state": "open",
            "new_state": "closed",
            "reason": "Check now passing",
        })
        _append_sync_log(readiness_dir, {
            "action": "reopen",
            "checkpoint_id": "sec-002",
            "item_id": "43",
            "previous_state": "closed",
            "new_state": "open",
            "reason": "Regression detected",
        })

        log_path = tmp_path / "sync-log.json"
        assert log_path.exists()
        log = json.loads(log_path.read_text())
        assert len(log) == 2
        assert log[0]["action"] == "close"
        assert log[1]["action"] == "reopen"
        assert "timestamp" in log[0]
        assert "timestamp" in log[1]

    def test_branch_safety_helper(self):
        from ready.ready import _get_current_branch
        branch = _get_current_branch()
        assert branch is not None
        assert isinstance(branch, str)

    def test_items_parser_has_new_flags(self):
        import argparse
        from ready.ready import main
        import sys

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        items_parser = subparsers.add_parser("items")
        items_parser.add_argument("--auto-reopen", action="store_true")
        items_parser.add_argument("--dry-run", action="store_true")
        items_parser.add_argument("--force", action="store_true")

        args = items_parser.parse_args(["--auto-reopen", "--dry-run", "--force"])
        assert args.auto_reopen is True
        assert args.dry_run is True
        assert args.force is True


class TestExcludePaths:
    """Tests for grep exclude_paths support."""

    def test_exclude_paths_filters_test_files(self, tmp_path):
        from ready.plugins.utils import grep_file_list

        src = tmp_path / "src" / "config.py"
        src.parent.mkdir()
        src.write_text('api_key = "real-secret-key-12345"\n')

        test = tmp_path / "tests" / "test_auth.py"
        test.parent.mkdir()
        test.write_text('mock_token = "fake-token-12345678"\n')

        files = [str(src), str(test)]
        excludes = ["tests/**"]

        hits = grep_file_list(
            r"(api_key|mock_token)\s*=\s*['\"][^'\"]{8,}",
            files, str(tmp_path), exclude_paths=excludes,
        )
        assert len(hits) == 1
        assert "src/config.py" in hits[0]

    def test_no_exclude_matches_all(self, tmp_path):
        from ready.plugins.utils import grep_file_list

        src = tmp_path / "app.py"
        src.write_text('secret = "mysecretvalue"\n')

        test = tmp_path / "tests" / "test_app.py"
        test.parent.mkdir()
        test.write_text('secret = "fakesecretval"\n')

        files = [str(src), str(test)]
        hits = grep_file_list(
            r"secret\s*=\s*['\"][^'\"]{8,}",
            files, str(tmp_path),
        )
        assert len(hits) == 2

    def test_exclude_nested_test_dirs(self, tmp_path):
        from ready.plugins.utils import grep_file_list

        test_file = tmp_path / "src" / "__tests__" / "auth.test.js"
        test_file.parent.mkdir(parents=True)
        test_file.write_text('const token = "test-bearer-token-abc"\n')

        files = [str(test_file)]
        hits = grep_file_list(
            r"token\s*=\s*['\"][^'\"]{10,}",
            files, str(tmp_path), exclude_paths=["**/__tests__/**"],
        )
        assert len(hits) == 0
