"""Shared helpers used by multiple verification plugins.

These are kept separate from the plugin base so plugins can import them
without circular-importing the registry. All helpers are filesystem
primitives — glob resolution, grep, dependency-directory filtering.
"""

import glob
import os
import re
from pathlib import Path


SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", ".env",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", "bin", "obj", "out", "target",
    ".idea", ".vscode", ".vs",
    "vendor", "third_party", "bower_components",
}


def is_skipped(path: str) -> bool:
    """Return True if any component of `path` is a dependency directory."""
    return any(part in SKIP_DIRS for part in Path(path).parts)


def _split_top_level(pattern: str) -> list[str]:
    """Split a pattern on commas that are outside brace groups."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in pattern:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    parts.append("".join(current).strip())
    return [p for p in parts if p]


def resolve_glob(pattern: str, repo_root: str) -> list[str]:
    """Resolve a glob pattern against the repo with brace expansion.

    Supports comma-separated patterns at the top level and brace
    expansion inside patterns. Automatically filters out dependency
    and tooling directories.
    """
    top_parts = _split_top_level(pattern)
    if len(top_parts) > 1:
        results: list[str] = []
        seen: set[str] = set()
        for part in top_parts:
            for m in resolve_glob(part, repo_root):
                if m not in seen:
                    seen.add(m)
                    results.append(m)
        return results

    if "{" in pattern and "}" in pattern:
        brace_match = re.search(r"\{([^}]+)\}", pattern)
        if brace_match:
            alternatives = brace_match.group(1).split(",")
            prefix = pattern[: brace_match.start()]
            suffix = pattern[brace_match.end() :]
            results = []
            for alt in alternatives:
                expanded = prefix + alt.strip() + suffix
                results.extend(resolve_glob(expanded, repo_root))
            return results

    full_pattern = os.path.join(repo_root, pattern)
    matches = glob.glob(full_pattern, recursive=True)
    repo_root_abs = os.path.abspath(repo_root)
    return [
        m for m in matches
        if not is_skipped(os.path.relpath(m, repo_root_abs))
    ]


def resolve_evidence_paths(
    verification: dict, repo_root: str, default: str = "**/*"
) -> list[str]:
    """Resolve file paths from `evidence_paths` (string or list) or `target`.

    evidence_paths takes precedence over target. A list is resolved
    element by element — users never need brace expansion syntax.
    """
    evidence_paths = verification.get("evidence_paths")
    if evidence_paths is not None:
        if isinstance(evidence_paths, list):
            result: list[str] = []
            for ep in evidence_paths:
                result.extend(resolve_glob(str(ep), repo_root))
            return result
        return resolve_glob(str(evidence_paths), repo_root)
    target = verification.get("target", default)
    return resolve_glob(target, repo_root)


def _matches_exclude(rel_path: str, exclude_patterns: list[str]) -> bool:
    """Return True if rel_path matches any of the exclude glob patterns."""
    from fnmatch import fnmatch
    for pat in exclude_patterns:
        if fnmatch(rel_path, pat):
            return True
        if "/" not in pat and fnmatch(Path(rel_path).name, pat):
            return True
    return False


def grep_file_list(
    pattern: str,
    target_files: list[str],
    repo_root: str,
    exclude_paths: list[str] | None = None,
) -> list[str]:
    """Grep a regex across a pre-resolved file list, returning rel-path:line hits."""
    evidence: list[str] = []
    for filepath in target_files:
        if not os.path.isfile(filepath):
            continue
        rel = os.path.relpath(filepath, repo_root)
        if exclude_paths and _matches_exclude(rel, exclude_paths):
            continue
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        evidence.append(f"{rel}:{line_num}")
        except (IOError, OSError):
            continue
    return evidence
