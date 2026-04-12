"""file_exists verification — pattern must resolve to at least one file."""

import os

from ready.plugins.base import PluginContext, VerificationPlugin, VerificationResult
from ready.plugins.utils import resolve_glob


class FileExistsPlugin(VerificationPlugin):
    method_name = "file_exists"

    def verify(self, checkpoint: dict, context: PluginContext) -> VerificationResult:
        verification = checkpoint.get("verification", {})
        pattern = verification.get("pattern", "")
        matches = resolve_glob(pattern, context.repo_root)
        evidence = [
            os.path.relpath(m, context.repo_root) for m in matches
        ]
        return VerificationResult(passed=len(matches) > 0, evidence=evidence)
