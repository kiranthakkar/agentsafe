# Contributing to agentsafe

Thanks for your interest in improving `agentsafe`. This document covers how
to set up a dev environment, the project's testing and style conventions,
how to add a new KMS provider, and how to report bugs or security issues.

`CLAUDE.md` is this repository's architecture guide and source of truth for
design decisions — skim it before making a non-trivial change, and update it
in the same PR if your change alters something it documents. This file is
the shorter, contributor-facing companion to it.

## Before you start

- For a bug fix or small improvement, feel free to open a PR directly.
- For a new feature or a change to existing behavior (especially anything
  touching settings resolution, file formats, or security requirements),
  please open an issue first to discuss the approach. This project has a
  deliberately small, considered surface area — see "Out of scope for v1"
  in `CLAUDE.md` for things that have already been discussed and declined.
- Security-sensitive reports (anything that could leak plaintext secrets,
  key material, or bypass a security requirement listed in `CLAUDE.md`)
  should **not** be filed as a public issue. Use GitHub's private
  vulnerability reporting (the "Report a vulnerability" option under this
  repo's Security tab) instead.

## Development setup

Requires Python 3.10+.

```console
git clone https://github.com/kiranthakkar/agentsafe.git
cd agentsafe
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

`.[dev]` pulls in the OCI provider extra plus `pytest`, `ruff`, and `mypy`.

## Running the checks

Run all three before opening a PR — none of them are currently enforced by
CI (there's no test workflow yet, only the release-time build check), so a
green local run is what maintainer review relies on:

```console
pytest
ruff check .
ruff format .
mypy src/agentsafe
```

## Testing conventions

- **Test the provider-agnostic logic once**, against the `KMSProvider`
  contract (`tests/test_kms_contract.py`), using a trivial fake in-memory
  provider — no real crypto, no cloud-specific mocking library.
- **Each concrete provider gets its own thin test file** that only verifies
  it maps correctly to/from its cloud SDK's request/response shape
  (`unittest.mock.patch` on that SDK's client — see `tests/test_kms_oci.py`).
  Don't reach for a provider-specific mocking framework (e.g. `moto`) for
  this; a handful of `SimpleNamespace` fakes is enough.
- **Never make a real KMS call from a unit test.** If you're adding
  integration-style tests that need live credentials, gate them behind an
  explicit marker or environment variable (e.g.
  `AGENTSAFE_RUN_INTEGRATION=1`) so `pytest` stays fast and offline by
  default.
- `tests/test_store.py` / `tests/test_envstore.py` and `tests/test_sdk.py` /
  `tests/test_env.py` mirror each other — `appconfig` (JSON) and `.env`
  (dotenv) are parallel stores with matching CRUD semantics, so a fix or
  test added to one side usually has an equivalent on the other.

## Code conventions

- Type hints on all public functions/methods; docstrings on the public SDK
  surface (`AgentSafe` and its methods, the `env` module's functions).
- Raise typed exceptions from `agentsafe.exceptions` (`KeyNotFoundError`,
  `KMSError`, `ConfigError`, ...) — never a bare `Exception`/`ValueError`.
- Keep `store.py`/`envstore.py` (file formats) and `kms/` (provider calls)
  decoupled from `sdk.py`/`env.py`/`cli.py` (user-facing surface), so each
  side can be tested and evolved independently.
- Don't add abstractions, config knobs, or fallback paths for hypothetical
  future needs — see the root `CLAUDE.md` for what's deliberately deferred
  and why, before reintroducing something that was already considered.

## Security requirements (non-negotiable)

These apply to any change, not just ones that look security-related at
first glance. The full list with rationale is in `CLAUDE.md`; the ones most
likely to matter for a typical PR:

- Plaintext secret values must never be written to disk, logs, shell
  history, or exception messages/tracebacks. The only two sanctioned
  exceptions are documented in CLAUDE.md's "`.env` support" section.
- Never invent local encryption or hold key material — every encrypt/decrypt
  call must go through a `KMSProvider`.
- Never swallow a KMS provider's authentication/authorization errors; wrap
  them in `KMSError`/`ConfigError` with exception chaining (`raise ... from
  error`), preserving the original as the cause.
- `list`/`env list` must never decrypt.
- New provider name collisions must be a hard error, never silently
  resolved by import order.
- Files written by agentsafe (`appconfig`, `.env`, `.agentsafe/config`,
  their temp files and lock files) must be created owner-readable/writable
  only (mode `0600`) where the OS supports it — see `store.py`/`envstore.py`/
  `config.py` for the established atomic-write pattern (temp file +
  `fsync` + `os.replace`/`os.link`) to follow for any new persisted file.

If you're unsure whether a change touches one of these, ask in the PR
description rather than guessing.

## Adding a new KMS provider

The plugin architecture is a first-class part of the public API — adding a
backend should never require touching `store.py`, `sdk.py`, `env.py`, or
`cli.py`. To add one:

1. Implement the `KMSProvider` protocol (`encrypt`/`decrypt`, see
   `src/agentsafe/kms/base.py`) in a new module.
2. Register it under the `agentsafe.kms_providers` entry-point group in your
   package's `pyproject.toml` (see this repo's own `oci_provider.py`
   registration for the pattern to dogfood).
3. Import your cloud SDK lazily, inside `__init__`, not at module load time
   — selecting a provider whose SDK isn't installed should raise a clear
   `ConfigError`, not an `ImportError` at import time.
4. Validate required settings in `__init__` and raise `ConfigError` naming
   what's missing, matching `OCIProvider`'s pattern.
5. This can live in a separate PyPI package (e.g.
   `agentsafe-kms-hashicorp-vault`) — you don't need to add it to this repo
   at all unless you're proposing it as a new bundled/first-party provider.

## Commit and PR conventions

- Keep PRs focused on one change; avoid bundling an unrelated refactor with
  a bug fix.
- Write commit messages that explain *why*, not just *what*.
- If your change alters something documented in `CLAUDE.md` (a file format,
  a settings-resolution rule, a security requirement), update `CLAUDE.md`
  and `AGENTS.md` together in the same PR — they're kept as mirrors of each
  other aside from `AGENTS.md` omitting the Claude Code–specific "Agent
  skills" section at the top of `CLAUDE.md`.
- Update `README.md`/`examples/` if the change affects documented CLI or SDK
  usage.

## License

By contributing, you agree that your contributions will be licensed under
this project's [MIT License](LICENSE).
