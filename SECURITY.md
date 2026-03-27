# Security Policy

HexAgent agents execute shell commands and access filesystems — security is a core architectural concern, not an afterthought.

## Reporting a Vulnerability

If you discover a security vulnerability in HexAgent, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please email: **anqi.tang.ai@gmail.com**

Include:
- A description of the vulnerability
- Steps to reproduce the issue
- The potential impact
- Any suggested fixes (if applicable)

## Response Timeline

- **Acknowledgment**: Within 48 hours of your report
- **Initial assessment**: Within 5 business days
- **Resolution**: Depending on severity, typically within 30 days

## Scope

This policy applies to the HexAgent codebase hosted at [github.com/an7tang/hexagent](https://github.com/an7tang/hexagent).

### In Scope

- Vulnerabilities in the `hexagent` library code
- Security issues in the `hexagent_demo` application
- Sandbox escape vulnerabilities in Computer implementations
- Injection vulnerabilities in tool execution (command injection, path traversal, etc.)

### Out of Scope

- Vulnerabilities in third-party dependencies (report these to the respective maintainers)
- Issues that require physical access to the machine running HexAgent
- Social engineering attacks

## Security Considerations

HexAgent agents execute shell commands and file operations. When deploying HexAgent:

- **Use sandboxed execution environments** (E2B cloud sandbox or Lima VMs) for untrusted workloads
- **Never expose the agent API to the public internet** without authentication
- **Review agent permissions** — the PermissionGate framework allows restricting tool access
- **Protect API keys** — use environment variables or secure secret management, never commit secrets to source control
