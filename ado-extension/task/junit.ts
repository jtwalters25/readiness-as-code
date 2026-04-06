/**
 * junit.ts — Convert a ready ScanResult JSON payload to JUnit XML.
 *
 * Each checkpoint becomes one <testcase>:
 *   PASS            → clean <testcase/>
 *   FAIL (red/yellow) → <testcase><failure .../></testcase>
 *   SKIP / EXCEPTION  → <testcase><skipped .../></testcase>
 */

export interface CheckpointResult {
  checkpoint_id: string;
  title: string;
  status: "pass" | "fail" | "skip" | "exception";
  severity: "red" | "yellow" | "green";
  type: string;
  confidence: string;
  evidence: string[];
  message: string;
  fix_hint: string;
  doc_link: string;
  guideline: string;
  guideline_section: string;
}

export interface ScanSummary {
  total: number;
  passing: number;
  failing_red: number;
  failing_yellow: number;
  exceptions: number;
  skipped: number;
  readiness_pct: number;
}

export interface ScanResult {
  service_name: string;
  scan_time: string;
  summary: ScanSummary;
  results: CheckpointResult[];
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

export function convertToJUnit(result: ScanResult): string {
  const { service_name, summary, results } = result;
  const failures = summary.failing_red + summary.failing_yellow;
  const skipped = summary.exceptions + summary.skipped;

  const testcases = results
    .map((r) => {
      const name = escapeXml(r.title);
      const classname = escapeXml(r.guideline_section || r.guideline || "Readiness");

      if (r.status === "pass") {
        return `    <testcase name="${name}" classname="${classname}" time="0"/>`;
      }

      if (r.status === "fail") {
        const message = escapeXml(r.fix_hint || r.message || "Checkpoint failed");
        const type = escapeXml(r.severity);
        const evidenceLines = (r.evidence || []).map((e) => escapeXml(e)).join("\n");
        const body = [
          evidenceLines ? `Evidence:\n${evidenceLines}` : "",
          r.fix_hint ? `Fix: ${escapeXml(r.fix_hint)}` : "",
          r.doc_link ? `Docs: ${escapeXml(r.doc_link)}` : "",
        ]
          .filter(Boolean)
          .join("\n");

        return (
          `    <testcase name="${name}" classname="${classname}" time="0">\n` +
          `      <failure message="${message}" type="${type}">${body}</failure>\n` +
          `    </testcase>`
        );
      }

      // skip / exception
      const skipMsg = escapeXml(r.message || "Skipped");
      return (
        `    <testcase name="${name}" classname="${classname}" time="0">\n` +
        `      <skipped message="${skipMsg}"/>\n` +
        `    </testcase>`
      );
    })
    .join("\n");

  return (
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<testsuites name="${escapeXml(service_name)} Readiness" tests="${summary.total}" failures="${failures}" skipped="${skipped}">\n` +
    `  <testsuite name="Readiness" tests="${summary.total}" failures="${failures}" skipped="${skipped}">\n` +
    testcases + "\n" +
    `  </testsuite>\n` +
    `</testsuites>\n`
  );
}
