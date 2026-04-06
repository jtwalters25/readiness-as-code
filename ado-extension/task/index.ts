/**
 * index.ts — ADO pipeline task entry point for ready (readiness-as-code).
 *
 * Execution flow:
 *   1. Read task inputs
 *   2. Verify Python is available
 *   3. pip install ready
 *   4. Run: ready scan --json [--calibrate] [--pack X]
 *   5. Parse ScanResult JSON from stdout
 *   6. Set output variables (ready.score, ready.blocking, ready.warnings)
 *   7. Optionally publish JUnit test results
 *   8. Optionally publish baseline JSON as build artifact
 *   9. Fail or pass based on red count (and optionally yellow)
 */

import * as tl from "azure-pipelines-task-lib/task";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";
import { convertToJUnit, ScanResult } from "./junit";

async function run(): Promise<void> {
  try {
    // ── Inputs ────────────────────────────────────────────────────────────────
    const workingDirectory =
      tl.getPathInput("workingDirectory", false, false) ||
      tl.getVariable("Build.SourcesDirectory") ||
      process.cwd();

    const pack = tl.getInput("pack", false) || "";
    const calibrate = tl.getBoolInput("calibrate", false);
    const failOnYellow = tl.getBoolInput("failOnYellow", false);
    const publishResults = tl.getBoolInput("publishResults", false);
    const publishBaseline = tl.getBoolInput("publishBaseline", false);

    // ── Verify Python ─────────────────────────────────────────────────────────
    tl.debug("Checking Python availability");
    const pythonPath = tl.which("python3") || tl.which("python");
    if (!pythonPath) {
      tl.setResult(
        tl.TaskResult.Failed,
        "Python 3 is required but was not found. Add a UsePythonVersion task before this task."
      );
      return;
    }

    const pythonVersion = tl.execSync(pythonPath, ["--version"]);
    console.log(`Using Python: ${pythonVersion.stdout.trim() || pythonVersion.stderr.trim()}`);

    // ── Install ready ─────────────────────────────────────────────────────────
    console.log("Installing ready...");
    const pip = tl.which("pip3") || tl.which("pip");
    if (!pip) {
      tl.setResult(tl.TaskResult.Failed, "pip not found. Ensure Python and pip are installed.");
      return;
    }

    const installResult = tl.execSync(pip, ["install", "--quiet", "ready"]);
    if (installResult.code !== 0) {
      tl.setResult(tl.TaskResult.Failed, `pip install ready failed: ${installResult.stderr}`);
      return;
    }

    // ── Build scan command ────────────────────────────────────────────────────
    const readyBin = tl.which("ready");
    if (!readyBin) {
      tl.setResult(
        tl.TaskResult.Failed,
        "ready command not found after install. Check that Python scripts directory is on PATH."
      );
      return;
    }

    const scanArgs = ["scan", "--json"];
    if (calibrate) scanArgs.push("--calibrate");
    if (pack) scanArgs.push("--pack", pack);

    // ── Run scan ──────────────────────────────────────────────────────────────
    console.log(`Running: ready ${scanArgs.join(" ")}`);
    console.log(`Working directory: ${workingDirectory}`);

    let stdout = "";
    let stderr = "";

    const scanCode = await tl.exec(readyBin, scanArgs, {
      cwd: workingDirectory,
      silent: false,
      outStream: {
        write: (s: string) => {
          stdout += s;
          process.stdout.write(s);
        },
      } as NodeJS.WritableStream,
      errStream: {
        write: (s: string) => {
          stderr += s;
          process.stderr.write(s);
        },
      } as NodeJS.WritableStream,
      ignoreReturnCode: true,
    });

    tl.debug(`Scan exit code: ${scanCode}`);

    // ── Parse JSON output ─────────────────────────────────────────────────────
    let result: ScanResult;
    try {
      // ready scan --json may include log lines before the JSON block
      const jsonStart = stdout.indexOf("{");
      const jsonEnd = stdout.lastIndexOf("}");
      if (jsonStart === -1 || jsonEnd === -1) {
        throw new Error("No JSON object found in scan output");
      }
      const jsonStr = stdout.slice(jsonStart, jsonEnd + 1);
      result = JSON.parse(jsonStr) as ScanResult;
    } catch (e) {
      tl.setResult(
        tl.TaskResult.Failed,
        `Failed to parse ready scan output as JSON. stderr: ${stderr}\nstdout: ${stdout}`
      );
      return;
    }

    const { summary } = result;

    // ── Output variables ──────────────────────────────────────────────────────
    tl.setVariable("ready.score", String(summary.readiness_pct), false, true);
    tl.setVariable("ready.blocking", String(summary.failing_red), false, true);
    tl.setVariable("ready.warnings", String(summary.failing_yellow), false, true);

    console.log(`\nReadiness: ${summary.readiness_pct}%  |  Blocking: ${summary.failing_red}  |  Warnings: ${summary.failing_yellow}`);

    // ── Publish JUnit test results ────────────────────────────────────────────
    if (publishResults) {
      try {
        const junitXml = convertToJUnit(result);
        const tmpDir = os.tmpdir();
        const junitPath = path.join(tmpDir, "readiness-junit.xml");
        fs.writeFileSync(junitPath, junitXml, "utf8");

        // ##vso[results.publish] logging command
        tl.command(
          "results.publish",
          {
            type: "JUnit",
            mergeResults: "false",
            runTitle: `Readiness — ${result.service_name}`,
            publishRunAttachments: "true",
          },
          junitPath
        );

        console.log(`Published ${result.results.length} checkpoint results as test cases.`);
      } catch (e) {
        tl.warning(`Failed to publish test results: ${e}`);
      }
    }

    // ── Publish baseline artifact ─────────────────────────────────────────────
    if (publishBaseline) {
      try {
        const stagingDir =
          tl.getVariable("Build.ArtifactStagingDirectory") || os.tmpdir();
        const artifactPath = path.join(stagingDir, "readiness-scan.json");

        fs.writeFileSync(
          artifactPath,
          JSON.stringify(result, null, 2),
          "utf8"
        );

        // ##vso[artifact.upload] logging command
        tl.command(
          "artifact.upload",
          { artifactname: "readiness-scan", artifacttype: "container" },
          artifactPath
        );

        console.log(`Published baseline artifact: readiness-scan`);
      } catch (e) {
        tl.warning(`Failed to publish baseline artifact: ${e}`);
      }
    }

    // ── Pass / Fail ───────────────────────────────────────────────────────────
    if (calibrate) {
      tl.setResult(
        tl.TaskResult.Succeeded,
        `Readiness scan complete (calibrate mode): ${summary.readiness_pct}%`
      );
      return;
    }

    const shouldFail =
      summary.failing_red > 0 || (failOnYellow && summary.failing_yellow > 0);

    if (shouldFail) {
      const reasons: string[] = [];
      if (summary.failing_red > 0) reasons.push(`${summary.failing_red} blocking failure(s)`);
      if (failOnYellow && summary.failing_yellow > 0)
        reasons.push(`${summary.failing_yellow} warning(s)`);
      tl.setResult(
        tl.TaskResult.Failed,
        `Readiness scan failed: ${reasons.join(", ")}. Score: ${summary.readiness_pct}%`
      );
    } else {
      tl.setResult(
        tl.TaskResult.Succeeded,
        `Readiness scan passed: ${summary.readiness_pct}%`
      );
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    tl.setResult(tl.TaskResult.Failed, `Unexpected error: ${message}`);
  }
}

run();
