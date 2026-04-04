"""
Azure DevOps adapter for ready work item tracking.

Requires: AZURE_DEVOPS_PAT and AZURE_DEVOPS_ORG environment variables.
"""

import json
import os
import base64
import urllib.request
import urllib.error
from typing import Optional

from . import WorkItemAdapter, WorkItemDraft, WorkItemResult


class AzureDevOpsAdapter(WorkItemAdapter):
    """Create and track readiness gaps as Azure DevOps work items (PBIs/Bugs)."""

    def __init__(
        self,
        org: str | None = None,
        project: str | None = None,
        pat: str | None = None,
        work_item_type: str = "Product Backlog Item",
    ):
        self.org = org or os.environ.get("AZURE_DEVOPS_ORG", "")
        self.project = project or os.environ.get("AZURE_DEVOPS_PROJECT", "")
        self.pat = pat or os.environ.get("AZURE_DEVOPS_PAT", "")
        self.work_item_type = work_item_type
        self.api_base = f"https://dev.azure.com/{self.org}/{self.project}/_apis"

        if not self.org or not self.project:
            raise ValueError(
                "Azure DevOps org and project required. "
                "Set AZURE_DEVOPS_ORG and AZURE_DEVOPS_PROJECT env vars."
            )

    def _headers(self) -> dict:
        creds = base64.b64encode(f":{self.pat}".encode()).decode()
        return {
            "Content-Type": "application/json-patch+json",
            "Authorization": f"Basic {creds}",
        }

    def _request(self, method: str, path: str, data=None) -> dict:
        url = f"{self.api_base}{path}"
        if "?" in url:
            url += "&api-version=7.1"
        else:
            url += "?api-version=7.1"

        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(
            url, data=body, headers=self._headers(), method=method
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            raise RuntimeError(f"ADO API error {e.code}: {error_body}") from e

    def create_draft(self, draft: WorkItemDraft) -> WorkItemResult:
        description = (
            f"<b>Checkpoint:</b> {draft.checkpoint_id}<br>"
            f"<b>Severity:</b> {draft.severity.upper()}<br>"
            f"<b>Guideline:</b> {draft.guideline} — {draft.guideline_section}<br><br>"
            f"{draft.description}<br><br>"
            f"<b>Evidence:</b><ul>{''.join(f'<li>{e}</li>' for e in draft.evidence)}</ul>"
            f"<b>Fix:</b> {draft.fix_hint}"
        )
        if draft.doc_link:
            description += f'<br><br><a href="{draft.doc_link}">Documentation</a>'

        patch_doc = [
            {"op": "add", "path": "/fields/System.Title", "value": f"[{draft.severity.upper()}] {draft.title}"},
            {"op": "add", "path": "/fields/System.Description", "value": description},
            {"op": "add", "path": "/fields/System.Tags", "value": f"readiness-gap; {draft.checkpoint_id}; severity:{draft.severity}"},
        ]

        result = self._request(
            "POST",
            f"/wit/workitems/${self.work_item_type}",
            patch_doc,
        )

        wi_id = str(result["id"])
        url = result.get("_links", {}).get("html", {}).get("href", "")

        return WorkItemResult(
            id=wi_id,
            url=url,
            status=result.get("fields", {}).get("System.State", "New"),
            checkpoint_id=draft.checkpoint_id,
        )

    def get_status(self, item_id: str) -> Optional[WorkItemResult]:
        try:
            result = self._request("GET", f"/wit/workitems/{item_id}")
            fields = result.get("fields", {})
            tags = fields.get("System.Tags", "")
            cp_id = ""
            for tag in tags.split(";"):
                tag = tag.strip()
                if tag.startswith("cp:") or (len(tag) > 3 and "-" in tag and tag[0].isalpha()):
                    cp_id = tag
                    break

            return WorkItemResult(
                id=str(result["id"]),
                url=result.get("_links", {}).get("html", {}).get("href", ""),
                status=fields.get("System.State", "Unknown"),
                checkpoint_id=cp_id,
            )
        except RuntimeError:
            return None

    def list_open(self, label: str | None = None) -> list[WorkItemResult]:
        tag_filter = "readiness-gap"
        if label:
            tag_filter += f" AND {label}"

        wiql = {
            "query": (
                f"SELECT [System.Id] FROM WorkItems "
                f"WHERE [System.Tags] CONTAINS '{tag_filter}' "
                f"AND [System.State] <> 'Closed' AND [System.State] <> 'Done' "
                f"ORDER BY [System.CreatedDate] DESC"
            )
        }

        # WIQL uses regular JSON content type
        url = f"{self.api_base}/wit/wiql?api-version=7.1"
        body = json.dumps(wiql).encode("utf-8")
        headers = self._headers()
        headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError:
            return []

        items = []
        for wi in data.get("workItems", []):
            status = self.get_status(str(wi["id"]))
            if status:
                items.append(status)

        return items

    def close(self, item_id: str, reason: str = "Resolved by scan") -> bool:
        try:
            patch_doc = [
                {"op": "add", "path": "/fields/System.State", "value": "Closed"},
                {"op": "add", "path": "/fields/System.History", "value": reason},
            ]
            self._request("PATCH", f"/wit/workitems/{item_id}", patch_doc)
            return True
        except RuntimeError:
            return False
