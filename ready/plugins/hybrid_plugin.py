"""Hybrid verification — both a code check AND an external attestation must pass.

Dispatches the nested `code_verification` block through the plugin
registry, then combines the result with an external attestation check.
Inherits confidence from the nested code block when the outer block
does not specify its own.
"""

from ready.plugins.base import Confidence, PluginContext, VerificationPlugin, VerificationResult
from ready.plugins.external_plugin import ExternalAttestationPlugin


class HybridPlugin(VerificationPlugin):
    method_name = "hybrid"

    def verify(self, checkpoint: dict, context: PluginContext) -> VerificationResult:
        verification = checkpoint.get("verification", {})
        code_ver = verification.get("code_verification", {})
        code_method = code_ver.get("method", "")

        # Inherit confidence from the nested code block if the outer block
        # does not specify its own. Hybrid checkpoints typically carry
        # confidence on the code check (e.g. "likely" for pattern-based greps),
        # not on the outer wrapper — the scanner must recurse into the nested
        # block to pick it up.
        inherited_confidence: Confidence | None = None
        if "confidence" not in verification and "confidence" in code_ver:
            try:
                inherited_confidence = Confidence(code_ver.get("confidence", "verified"))
            except ValueError:
                inherited_confidence = None

        code_plugin = (
            context.registry.get(code_method) if context.registry else None
        )

        if code_plugin is None:
            code_passed = False
            code_evidence = [
                f"Unknown code verification method: '{code_method or '(none)'}'. "
                "Hybrid checkpoints require a 'code_verification' block with a "
                "valid method (grep, glob, file_exists, etc.)."
            ]
        else:
            # Build a shim checkpoint so the nested plugin sees its block as the
            # top-level verification — avoids leaking hybrid structure into plugins.
            shim_checkpoint = {
                "id": checkpoint.get("id", ""),
                "title": checkpoint.get("title", ""),
                "verification": code_ver,
            }
            code_result = code_plugin.verify(shim_checkpoint, context)
            code_passed = code_result.passed
            code_evidence = code_result.evidence

        external_result = ExternalAttestationPlugin().verify(checkpoint, context)
        ext_passed = external_result.passed
        ext_evidence = external_result.evidence

        combined_evidence = [f"[code] {e}" for e in code_evidence] + [
            f"[external] {e}" for e in ext_evidence
        ]

        return VerificationResult(
            passed=(code_passed and ext_passed),
            evidence=combined_evidence,
            confidence=inherited_confidence,
        )
