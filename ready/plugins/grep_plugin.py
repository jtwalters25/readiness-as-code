"""grep, grep_all, and grep_count verification methods.

- grep: pattern must appear at least `min_matches` times across target files.
        Supports `pass_condition: absent` for negative checks, and the legacy
        `min_matches: 0` form (also a negative check).
- grep_all: every pattern in `patterns` must appear in target files.
- grep_count: alias for grep (kept for intent clarity in checkpoint files).
"""

from ready.plugins.base import PluginContext, VerificationPlugin, VerificationResult
from ready.plugins.utils import grep_file_list, resolve_evidence_paths


class GrepPlugin(VerificationPlugin):
    method_name = "grep"

    def verify(self, checkpoint: dict, context: PluginContext) -> VerificationResult:
        verification = checkpoint.get("verification", {})
        pattern = verification.get("pattern", "")
        min_matches = verification.get("min_matches", 1)
        pass_condition = verification.get("pass_condition", "present")

        target_files = resolve_evidence_paths(verification, context.repo_root)
        evidence = grep_file_list(pattern, target_files, context.repo_root)

        if pass_condition == "absent":
            return VerificationResult(passed=(len(evidence) == 0), evidence=evidence)

        if min_matches == 0:
            # Legacy: min_matches=0 was used for secrets detection
            return VerificationResult(passed=(len(evidence) == 0), evidence=evidence)

        return VerificationResult(
            passed=(len(evidence) >= min_matches),
            evidence=evidence,
        )


class GrepAllPlugin(VerificationPlugin):
    method_name = "grep_all"

    def verify(self, checkpoint: dict, context: PluginContext) -> VerificationResult:
        verification = checkpoint.get("verification", {})
        patterns = verification.get("patterns", [])
        target_files = resolve_evidence_paths(verification, context.repo_root)
        all_evidence: list[str] = []
        for pattern in patterns:
            hits = grep_file_list(pattern, target_files, context.repo_root)
            if not hits:
                return VerificationResult(
                    passed=False,
                    evidence=[f"Pattern not found: {pattern}"],
                )
            all_evidence.extend(hits)
        return VerificationResult(passed=True, evidence=all_evidence)


class GrepCountPlugin(VerificationPlugin):
    method_name = "grep_count"

    def verify(self, checkpoint: dict, context: PluginContext) -> VerificationResult:
        return GrepPlugin().verify(checkpoint, context)
