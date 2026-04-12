"""file_count verification — alias for glob with the same semantics.

Kept as a distinct plugin so callers can express intent ("count files"
vs "match glob"); behavior is identical to GlobPlugin.
"""

from ready.plugins.base import PluginContext, VerificationPlugin, VerificationResult
from ready.plugins.glob_plugin import GlobPlugin


class FileCountPlugin(VerificationPlugin):
    method_name = "file_count"

    def verify(self, checkpoint: dict, context: PluginContext) -> VerificationResult:
        return GlobPlugin().verify(checkpoint, context)
