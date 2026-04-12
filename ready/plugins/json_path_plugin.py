"""json_path verification — read a dotted path out of a JSON file and optionally compare."""

import json
import os

from ready.plugins.base import PluginContext, VerificationPlugin, VerificationResult


class JsonPathPlugin(VerificationPlugin):
    method_name = "json_path"

    def verify(self, checkpoint: dict, context: PluginContext) -> VerificationResult:
        verification = checkpoint.get("verification", {})
        target = verification.get("target", "")
        json_path_expr = verification.get("json_path", "")
        expected = verification.get("expected_value")

        target_path = os.path.join(context.repo_root, target)
        if not os.path.isfile(target_path):
            return VerificationResult(passed=False, evidence=[f"File not found: {target}"])

        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            keys = json_path_expr.strip("$.").split(".")
            current = data
            for key in keys:
                if isinstance(current, dict):
                    current = current.get(key)
                elif isinstance(current, list) and key.isdigit():
                    current = current[int(key)]
                else:
                    return VerificationResult(
                        passed=False,
                        evidence=[f"Path {json_path_expr} not found in {target}"],
                    )

            if expected is not None:
                return VerificationResult(
                    passed=(current == expected),
                    evidence=[f"{target}: {json_path_expr} = {current}"],
                )
            return VerificationResult(
                passed=(current is not None),
                evidence=[f"{target}: {json_path_expr} = {current}"],
            )
        except (json.JSONDecodeError, IOError) as e:
            return VerificationResult(
                passed=False,
                evidence=[f"Error reading {target}: {e}"],
            )
