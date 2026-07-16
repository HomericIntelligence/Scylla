# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in Scylla, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

1. **Email**: Send details to [research@villmow.us](mailto:research@villmow.us)
2. **Subject line**: `[SECURITY] Scylla - Brief description`
3. **Include**:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

### What to Expect

- **Acknowledgment**: Within 48 hours
- **Assessment**: Within 1 week
- **Resolution**: Depends on severity; critical issues targeted within 2 weeks

### Scope

The following are in scope for security reports:

- API key exposure or credential leakage
- Command injection in CLI or subprocess calls
- Unsafe deserialization of experiment data
- Docker container escape or privilege escalation
- Dependencies with known CVEs not covered by pip-audit

### Out of Scope

- Vulnerabilities in third-party services (Anthropic API, OpenAI API)
- Issues requiring physical access to the machine
- Social engineering attacks

## Data Sent to Third Parties

When Scylla runs evaluations it sends data to the **Anthropic API**:

- **Prompts**: system prompts, task descriptions, and any CLAUDE.md content included in the run
- **Repository content**: file snippets and code passed to the agent as context during test execution
- **Agent outputs**: intermediate tool calls, reasoning traces, and final responses (used as judge inputs)

No data is sent to third-party services other than the Anthropic API unless you explicitly configure
additional MCP servers or tool integrations.

Users are responsible for ensuring that repository content included in prompts complies with their
organisation's data-handling policies before running evaluations against the Anthropic API.

Refer to [Anthropic's usage policies](https://www.anthropic.com/legal/usage-policy) and
[privacy policy](https://www.anthropic.com/legal/privacy) for details on how submitted data is handled.

For guidance on what experiment outputs are stored locally and how long to retain them, see
[docs/dev/data-policy.md](docs/dev/data-policy.md).

## Security Practices

Scylla follows these security practices:

- **No hardcoded secrets**: API keys read from environment variables
- **No shell=True**: All subprocess calls use list-based arguments
- **CVE scanning**: pip-audit runs in CI and pre-commit hooks
- **Credential isolation**: Context-managed temporary credential mounts with restricted permissions
- **Docker security**: Non-root user, SHA256-pinned base images, health checks
