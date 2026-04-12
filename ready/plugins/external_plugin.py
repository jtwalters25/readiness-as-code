"""external_attestation verification — look up a human attestation in the evidence registry."""

from datetime import date, datetime

from ready.plugins.base import PluginContext, VerificationPlugin, VerificationResult


class ExternalAttestationPlugin(VerificationPlugin):
    method_name = "external_attestation"

    def verify(self, checkpoint: dict, context: PluginContext) -> VerificationResult:
        verification = checkpoint.get("verification", {})
        key = verification.get("attestation_key", "")
        attestations = context.evidence_registry.get("attestations", [])

        for att in attestations:
            if att.get("checkpoint_id") == key or att.get("attestation_key") == key:
                expires = att.get("expires")
                if expires:
                    try:
                        exp_date = datetime.strptime(expires, "%Y-%m-%d").date()
                        if exp_date < date.today():
                            return VerificationResult(
                                passed=False,
                                evidence=[
                                    f"Attestation by {att.get('attested_by')} expired on {expires}"
                                ],
                            )
                    except ValueError:
                        pass
                return VerificationResult(
                    passed=True,
                    evidence=[
                        f"Attested by {att.get('attested_by')} on {att.get('attested_date')}: {att.get('evidence_link', 'no link')}"
                    ],
                )

        return VerificationResult(
            passed=False,
            evidence=[f"No attestation found for '{key}' in external-evidence.json"],
        )
