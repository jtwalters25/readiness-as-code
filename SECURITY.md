# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

To report a vulnerability, email the details to the maintainer via GitHub's private vulnerability reporting:

1. Go to the [Security tab](https://github.com/jtwalters25/readiness-as-code/security)
2. Click **"Report a vulnerability"**
3. Fill in the details

You can expect an acknowledgment within **48 hours** and a resolution timeline within **7 days** for confirmed issues.

Please include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fix (optional)

## Scope

This tool scans local repositories — it does not make outbound network calls except when using work item adapters (GitHub Issues, Azure DevOps), which require explicit user configuration and credentials. 

Out of scope: issues in third-party dependencies (report those upstream).
