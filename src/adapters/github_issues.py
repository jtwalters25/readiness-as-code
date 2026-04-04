"""
GitHub Issues adapter for readiness-as-code work item tracking.

Requires: GITHUB_TOKEN environment variable with repo scope.
"""

import json
import os
import urllib.request
import urllib.error
from typing import Optional

from . import WorkItemAdapter, WorkItemDraft, WorkItemResult


class GitHubIssuesAdapter(WorkItemAdapter):
    """Create and track readiness gaps as GitHub Issues."""

    def __init__(self, repo: str | None = None, token: str | None = None):
        """
        Args:
            repo: GitHub repo in 'owner/name' format. Falls back to GITHUB_REPOSITORY env var.
            token: GitHub token. Falls back to GITHUB_TOKEN env var.
        """
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.api_base = f"https://api.github.com/repos/{self.repo}"

        if not self.repo:
            raise ValueError(
                "GitHub repo required. Set GITHUB_REPOSITORY or pass repo='owner/name'"
            )

    def _headers(self) -> dict:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, data: dict | None = None) -> dict:
        url = f"{self.api_base}{path}"
        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(
            url, data=body, headers=self._headers(), method=method
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(
                f"GitHub API error {e.code}: {error_body}"
            ) from e

    def create_draft(self, draft: WorkItemDraft) -> WorkItemResult:
        body_parts = [
            f"**Checkpoint:** `{draft.checkpoint_id}`",
            f"**Severity:** {draft.severity.upper()}",
            f"**Guideline:** {draft.guideline} — {draft.guideline_section}",
            "",
            draft.description,
            "",
            "### Evidence",
            *[f"- `{e}`" for e in draft.evidence],
            "",
            "### Fix",
            draft.fix_hint,
        ]
        if draft.doc_link:
            body_parts.extend(["", f"**Docs:** {draft.doc_link}"])

        body_parts.append(
            "\n\n---\n*Created by [readiness-as-code](https://github.com/jtwalters25/readiness-as-code)*"
        )

        labels = ["readiness-gap", f"severity:{draft.severity}"] + draft.labels

        data = {
            "title": f"[{draft.severity.upper()}] {draft.title}",
            "body": "\n".join(body_parts),
            "labels": labels,
        }

        result = self._request("POST", "/issues", data)
        return WorkItemResult(
            id=str(result["number"]),
            url=result["html_url"],
            status=result["state"],
            checkpoint_id=draft.checkpoint_id,
        )

    def get_status(self, item_id: str) -> Optional[WorkItemResult]:
        try:
            result = self._request("GET", f"/issues/{item_id}")
            # Find checkpoint_id from labels
            cp_id = ""
            for label in result.get("labels", []):
                name = label.get("name", "") if isinstance(label, dict) else label
                if name.startswith("cp:"):
                    cp_id = name[3:]
                    break

            return WorkItemResult(
                id=str(result["number"]),
                url=result["html_url"],
                status=result["state"],
                checkpoint_id=cp_id,
            )
        except RuntimeError:
            return None

    def list_open(self, label: str | None = None) -> list[WorkItemResult]:
        path = "/issues?state=open&labels=readiness-gap"
        if label:
            path += f",{label}"

        results = self._request("GET", path)
        items = []
        for issue in results:
            cp_id = ""
            for lbl in issue.get("labels", []):
                name = lbl.get("name", "") if isinstance(lbl, dict) else lbl
                if name.startswith("cp:"):
                    cp_id = name[3:]
                    break

            items.append(
                WorkItemResult(
                    id=str(issue["number"]),
                    url=issue["html_url"],
                    status=issue["state"],
                    checkpoint_id=cp_id,
                )
            )
        return items

    def close(self, item_id: str, reason: str = "Resolved by scan") -> bool:
        try:
            self._request("POST", f"/issues/{item_id}/comments", {"body": reason})
            self._request("PATCH", f"/issues/{item_id}", {"state": "closed"})
            return True
        except RuntimeError:
            return False
