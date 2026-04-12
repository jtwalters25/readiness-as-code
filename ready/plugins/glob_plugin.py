"""glob and glob_all verification methods.

- glob: pattern must match at least `min_matches` files (default 1)
- glob_all: every pattern in `patterns` must match at least one file
"""

import os

from ready.plugins.base import PluginContext, VerificationPlugin, VerificationResult
from ready.plugins.utils import resolve_glob


class GlobPlugin(VerificationPlugin):
    method_name = "glob"

    def verify(self, checkpoint: dict, context: PluginContext) -> VerificationResult:
        verification = checkpoint.get("verification", {})
        pattern = verification.get("pattern", "")
        min_matches = verification.get("min_matches", 1)
        matches = resolve_glob(pattern, context.repo_root)
        evidence = [os.path.relpath(m, context.repo_root) for m in matches]
        return VerificationResult(
            passed=len(matches) >= min_matches,
            evidence=evidence,
        )


class GlobAllPlugin(VerificationPlugin):
    method_name = "glob_all"

    def verify(self, checkpoint: dict, context: PluginContext) -> VerificationResult:
        verification = checkpoint.get("verification", {})
        patterns = verification.get("patterns", [])
        all_evidence: list[str] = []
        for pattern in patterns:
            matches = resolve_glob(pattern, context.repo_root)
            if not matches:
                return VerificationResult(
                    passed=False,
                    evidence=[f"No files found matching: {pattern}"],
                )
            all_evidence.extend(
                os.path.relpath(m, context.repo_root) for m in matches
            )
        return VerificationResult(passed=True, evidence=all_evidence)
