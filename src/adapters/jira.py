"""
Jira adapter for readiness-as-code work item tracking.

Requires environment variables:
    JIRA_URL        Base URL of your Jira instance, e.g. https://your-org.atlassian.net
    JIRA_EMAIL      Atlassian account email
    JIRA_API_TOKEN  API token (generate at https://id.atlassian.com/manage-profile/security/api-tokens)
    JIRA_PROJECT    Project key (e.g. "OPS", "ENG") — or pass project= in constructor
"""

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Optional

from . import WorkItemAdapter, WorkItemDraft, WorkItemResult


class JiraAdapter(WorkItemAdapter):
    """Create and track readiness gaps as Jira issues."""

    def __init__(
        self,
        url: str | None = None,
        email: str | None = None,
        token: str | None = None,
        project: str | None = None,
        issue_type: str = "Task",
    ):
        """
        Args:
            url:        Jira base URL. Falls back to JIRA_URL env var.
            email:      Atlassian email. Falls back to JIRA_EMAIL env var.
            token:      API token. Falls back to JIRA_API_TOKEN env var.
            project:    Project key (e.g. "OPS"). Falls back to JIRA_PROJECT env var.
            issue_type: Jira issue type to create. Default: "Task".
        """
        self.url = (url or os.environ.get("JIRA_URL", "")).rstrip("/")
        self.email = email or os.environ.get("JIRA_EMAIL", "")
        self.token = token or os.environ.get("JIRA_API_TOKEN", "")
        self.project = project or os.environ.get("JIRA_PROJECT", "")
        self.issue_type = issue_type
        self.api_base = f"{self.url}/rest/api/3"

        if not self.url:
            raise ValueError("Jira URL required. Set JIRA_URL or pass url=")
        if not self.project:
            raise ValueError("Jira project key required. Set JIRA_PROJECT or pass project=")

    def _headers(self) -> dict:
        creds = base64.b64encode(f"{self.email}:{self.token}".encode()).decode()
        return {
            "Authorization": f"Basic {creds}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

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
            raise RuntimeError(f"Jira API error {e.code}: {error_body}") from e

    def create_draft(self, draft: WorkItemDraft) -> WorkItemResult:
        severity_emoji = "🔴" if draft.severity.lower() == "red" else "🟡"

        # Jira uses Atlassian Document Format (ADF) for rich description
        evidence_items = [
            {
                "type": "listItem",
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": e}]}],
            }
            for e in draft.evidence
        ]

        description_content = [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Checkpoint: ", "marks": [{"type": "strong"}]},
                    {"type": "text", "text": draft.checkpoint_id},
                ],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Severity: ", "marks": [{"type": "strong"}]},
                    {"type": "text", "text": f"{severity_emoji} {draft.severity.upper()}"},
                ],
            },
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Guideline: ", "marks": [{"type": "strong"}]},
                    {"type": "text", "text": f"{draft.guideline} — {draft.guideline_section}"},
                ],
            },
            {"type": "paragraph", "content": [{"type": "text", "text": draft.description}]},
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Evidence"}],
            },
            {"type": "bulletList", "content": evidence_items} if evidence_items else
            {"type": "paragraph", "content": [{"type": "text", "text": "No file evidence."}]},
            {
                "type": "heading",
                "attrs": {"level": 3},
                "content": [{"type": "text", "text": "Fix"}],
            },
            {"type": "paragraph", "content": [{"type": "text", "text": draft.fix_hint}]},
        ]

        if draft.doc_link:
            description_content.append({
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Docs: ", "marks": [{"type": "strong"}]},
                    {
                        "type": "text",
                        "text": draft.doc_link,
                        "marks": [{"type": "link", "attrs": {"href": draft.doc_link}}],
                    },
                ],
            })

        labels = ["readiness-gap", f"severity-{draft.severity.lower()}"] + [
            lbl.replace(" ", "-") for lbl in draft.labels
        ]

        payload = {
            "fields": {
                "project": {"key": self.project},
                "summary": f"[{draft.severity.upper()}] {draft.title}",
                "description": {
                    "version": 1,
                    "type": "doc",
                    "content": description_content,
                },
                "issuetype": {"name": self.issue_type},
                "labels": labels,
            }
        }

        result = self._request("POST", "/issue", payload)
        issue_key = result["key"]
        issue_url = f"{self.url}/browse/{issue_key}"

        return WorkItemResult(
            id=issue_key,
            url=issue_url,
            status="Open",
            checkpoint_id=draft.checkpoint_id,
        )

    def get_status(self, item_id: str) -> Optional[WorkItemResult]:
        try:
            result = self._request("GET", f"/issue/{item_id}")
            fields = result.get("fields", {})
            status = fields.get("status", {}).get("name", "Unknown")
            labels = fields.get("labels", [])
            cp_id = ""
            for label in labels:
                if label.startswith("cp-"):
                    cp_id = label[3:].replace("-", "-")
                    break

            return WorkItemResult(
                id=result["key"],
                url=f"{self.url}/browse/{result['key']}",
                status=status,
                checkpoint_id=cp_id,
            )
        except RuntimeError:
            return None

    def list_open(self, label: str | None = None) -> list[WorkItemResult]:
        label_filter = "readiness-gap"
        if label:
            label_filter = f"{label_filter} AND {label}"

        jql = (
            f'project = "{self.project}" '
            f'AND labels = "readiness-gap" '
            f'AND statusCategory != Done '
            f'ORDER BY created DESC'
        )
        if label:
            jql = (
                f'project = "{self.project}" '
                f'AND labels = "readiness-gap" '
                f'AND labels = "{label}" '
                f'AND statusCategory != Done '
                f'ORDER BY created DESC'
            )

        try:
            result = self._request(
                "POST",
                "/issue/picker" if False else "/search",
                {"jql": jql, "fields": ["summary", "status", "labels"], "maxResults": 100},
            )
        except RuntimeError:
            return []

        items = []
        for issue in result.get("issues", []):
            fields = issue.get("fields", {})
            status = fields.get("status", {}).get("name", "Unknown")
            labels = fields.get("labels", [])
            cp_id = ""
            for label in labels:
                if label.startswith("cp-"):
                    cp_id = label[3:]
                    break

            items.append(WorkItemResult(
                id=issue["key"],
                url=f"{self.url}/browse/{issue['key']}",
                status=status,
                checkpoint_id=cp_id,
            ))
        return items

    def close(self, item_id: str, reason: str = "Resolved by scan") -> bool:
        try:
            # Add comment
            self._request("POST", f"/issue/{item_id}/comment", {
                "body": {
                    "version": 1,
                    "type": "doc",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": reason}]}],
                }
            })

            # Get available transitions and find a "Done" state
            transitions = self._request("GET", f"/issue/{item_id}/transitions")
            done_id = None
            for t in transitions.get("transitions", []):
                if t.get("to", {}).get("statusCategory", {}).get("key") == "done":
                    done_id = t["id"]
                    break

            if done_id:
                self._request("POST", f"/issue/{item_id}/transitions", {
                    "transition": {"id": done_id}
                })
            return True
        except RuntimeError:
            return False
