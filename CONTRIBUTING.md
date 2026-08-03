# Contributing to ROTM — Resilient Offline Transaction Mesh

Thank you for your interest in contributing to ROTM! We welcome contributions from developers, cryptographers, and security researchers interested in offline payments, P2P mesh networking, and on-device AI.

---

## Code of Conduct

Please help us maintain a friendly, welcoming, and inclusive community. Treat all contributors with respect regardless of experience level.

---

## How to Contribute

### 1. Reporting Bugs & Security Vulnerabilities
- For general bugs or feature requests, open a GitHub Issue with clear reproduction steps.
- **Security Vulnerabilities:** If you discover a cryptographic or double-spend vulnerability, please do **NOT** open a public issue. Email the core maintainers privately or follow the security advisory process.

### 2. Setting Up Development Environment
```bash
# Clone repository
git clone https://github.com/your-username/rotm.git
cd rotm

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Running Test Suites
Before submitting a Pull Request, ensure all core and transport tests pass:

```bash
# Run core cryptographic and ledger tests
python tests/test_core.py

# Run device-to-device transport tests
python tests/test_transport.py

# Optional: Run pytest across all test suites
pytest tests/
```

### 4. Pull Request Guidelines
- Branch naming convention: `feature/short-description` or `fix/issue-description`.
- Keep PRs focused on a single logical change or feature.
- Ensure new code includes test coverage in `tests/`.
- Ensure all commit messages are clear and descriptive.
- Make sure `git status` shows no stray `wallet_state.json` or local state files.

---

## License

By contributing to ROTM, you agree that your contributions will be licensed under the project's [MIT License](LICENSE).
