# Security policy

## Report a vulnerability

Please do not disclose vulnerability details in public issues, pull requests, or discussions.

The intended reporting route is GitHub's private vulnerability reporting. Open the repository's [Security Advisories page](https://github.com/appunni-m/python-standard/security/advisories) and choose **Report a vulnerability**. GitHub currently reports private vulnerability reporting as disabled for this repository; the owner must enable it before the button is available. If it is missing, contact the maintainer through the [GitHub profile](https://github.com/appunni-m) to request a private reporting channel; do not send vulnerability details until a private channel is confirmed. GitHub's [private reporting guide](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/report-privately) describes the process.

Include the affected version, Python version, impact, and a minimal reproduction. Remove credentials, personal data, and unrelated sensitive information from the report.

## Supported versions

Only the latest patch release in the `0.1.x` line receives security fixes. The latest PyPI release is currently `0.1.0`. The project declares Python `>=3.11`; CI tests CPython 3.11 through 3.14.

## Response expectations

Maintainers aim to acknowledge a private report within five business days and provide an initial triage update within ten business days. These are response targets, not guarantees. For a confirmed issue, maintainers will coordinate impact assessment, a fix, and disclosure timing through the private report.
