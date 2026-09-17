# agentsafe

## Agent skills

### Issue tracker

Issues are local Markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical triage labels are used unchanged. See `docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository. See `docs/agents/domain.md`.

## What this is

`agentsafe` is a Python library for securely storing and retrieving configuration
parameters (API keys, connection strings, credentials, etc.) used by AI agent
applications. It never invents or holds its own encryption keys — every
encrypt/decrypt operation is delegated to a customer-managed key in a KMS
backend. **OCI Key Management Service (KMS)** is the first backend; AWS KMS,
GCP Cloud KMS, and Azure Key Vault are supported as pluggable alternatives
(see "KMS provider plugin architecture"). Encrypted values are persisted
project-locally, either to a JSON file named `appconfig` or, via the `.env`
integration (see "`.env` support"), to a standard-shaped `.env` file.

Agent developers use `agentsafe` two ways:
- **CLI** — `init`, `config`, `set`/`store`, `get`/`retrieve`, `remove` config parameters
  from a terminal or setup script, plus `env encrypt`/`env set`/`env get`/
  `env remove`/`env list` for the `.env`-based workflow.
- **SDK** — import `agentsafe` in a Python application to fetch decrypted
  config values at runtime, either via the `AgentSafe` class or the `env`
  module (`from agentsafe import env`) for `.env`-backed values.

> Status: v0.2.0 is published on PyPI as `agentconfigsafe`, with OCI KMS as
> the bundled provider. This file is the working architecture guide and source
> of truth for subsequent changes. Update it, rather than silently drifting
> from it, when a decision changes during implementation.
>
> v0.2.0 made three breaking/additive design changes relative to v0.1.2:
> project-local KMS settings (replacing the home-directory registry and the
> named-application/`--application` model with a single implicit profile per
> project — see "Settings & file locations"), a new `.env`/`.env.agent`
> KMS-backed store (see "`.env` support"), inspired by the workflow shape of
> the `envrypt` PyPI package but using agentsafe's existing KMS-backed
> `EncryptedBlob`/`KMSProvider` machinery instead of a local symmetric key
> (`envrypt` itself uses a locally stored/prompted XOR key, which is exactly
> the local-key risk agentsafe exists to eliminate — only its workflow shape,
> raw file → compiled file → `env.get()`, is reused, not its encryption
> model), and dropping `compartment` as an agentsafe setting entirely (see
> "Core concepts") since OCI's Encrypt/Decrypt calls never used it.

## Core concepts

- **KMS-backed encryption, no local keys.** `agentsafe` calls the configured
  provider's Encrypt/Decrypt API for every operation. It stores key/vault
  identifiers, never key material.
- **`appconfig` file.** The on-disk artifact holding a project's encrypted
  parameters — a **JSON** document mapping config names to provider-tagged
  ciphertext envelopes (see schema below). KMS configuration lives only in
  the project-local `.agentsafe/config` file. No plaintext secret value is
  ever written into this file. Chosen over YAML/TOML because it needs no
  extra dependency and the file is machine-written/machine-read only.
- **`.env` file (alternate store).** The same KMS-backed encryption, same
  `EncryptedBlob`/`KMSProvider` machinery, and the same project-local KMS
  settings, but persisted as a standard `KEY=value` dotenv file instead of
  JSON — for teams whose other tooling already auto-loads `.env`. See
  "`.env` support" below; `appconfig` and `.env` are independent, parallel
  stores, not two views of the same data.
- **OCI profile-based auth (for the OCI provider).** Relies on the standard
  OCI SDK/CLI config file (`~/.oci/config`) and profiles — `agentsafe` does
  not implement its own auth. Each provider owns its own auth mechanism (see
  below); "profile" is an OCI-specific concept, not a cross-provider one.
- **Three required OCI settings**, independently configurable by the end
  user (not hardcoded): **profile name**, **KMS vault crypto endpoint** (the
  per-vault URL used for Encrypt/Decrypt, distinct from the KMS management
  endpoint), and **KMS key OCID**. The key OCID is required for Encrypt; it
  is also recorded in each OCI ciphertext envelope so the correct key can be
  used for Decrypt. A compartment OCID is deliberately not one of these —
  OCI's Encrypt/Decrypt (crypto-plane) API takes only a key OCID and the
  vault's crypto endpoint; compartment scoping only matters for KMS
  management-plane calls (e.g. listing/creating keys), which agentsafe never
  makes.
- **Pluggable KMS backend via entry-point plugins.** See the dedicated
  section below — this is a first-class, public-API-level design constraint,
  not an implementation detail.

## KMS provider plugin architecture

OCI KMS is the first backend, not the only one, and the plugin model is
**fully open to third parties** — someone can `pip install
agentsafe-kms-hashicorp-vault` and it registers itself without any agentsafe
core change. This is a deliberate, documented public API, not just an
internal abstraction:

```python
# kms/base.py
class KMSProvider(Protocol):
    def encrypt(self, plaintext: str) -> EncryptedBlob: ...
    def decrypt(self, blob: EncryptedBlob) -> str: ...
```

**Discovery mechanism: `importlib.metadata` entry points**, group name
`agentsafe.kms_providers`. Each entry point maps a provider name (`"oci"`,
`"aws"`, ...) to a class implementing `KMSProvider`.

- **OCI is the only bundled and registered provider in v1.**
  `oci_provider.py` lives inside `agentsafe/kms/` and registers in the
  `agentsafe.kms_providers` entry-point group via an entry declared in
  `agentsafe`'s own `pyproject.toml` — dogfooding the exact mechanism a
  third party would use. AWS, GCP, and Azure are future providers and have no
  v1 modules or entry points.
- **Lazy loading — a provider SDK import happens only when that provider is selected.**
  Discovery (`importlib.metadata.entry_points(group="agentsafe.kms_providers")`)
  only reads entry-point *names*; it never calls `.load()` until that
  specific provider is chosen (via `AGENTSAFE_KMS_PROVIDER` or equivalent).
  Selecting OCI without its optional SDK installed raises a clear
  `ConfigError` (for example, `"provider 'oci' requires oci: pip install
  agentconfigsafe[oci]"`) at selection time.
- **Name collisions are a hard error at discovery time.** If two distinct
  entry points claim the same provider name (e.g. a third-party package
  also registers `"aws"`), raise a `ConfigError` naming both conflicting
  packages and require the user to uninstall one. Never silently shadow one
  provider with another — this is a security-critical selection, not a
  cosmetic conflict, so it must never resolve by implicit import order.
- **Each provider owns its own auth/config.** OCI: profile + crypto endpoint
  + key OCID. AWS: profile/region + key ARN. GCP: service account/ADC +
  key resource name. Azure: `DefaultAzureCredential` chain + vault URL +
  key name. `store.py`/`sdk.py`/`cli.py` never know these details.
- **The OCI SDK is an optional extra**: `agentconfigsafe[oci]`. Installing bare
  `agentsafe` pulls in no cloud-provider SDK. Future providers will add their
  own optional extras when implemented.
- **Adding a backend (built-in or third-party) never requires touching**
  `store.py`, `sdk.py`, or `cli.py` — only a new module implementing
  `KMSProvider` plus an entry-point registration.

### `EncryptedBlob` schema (the plugin contract)

Each `appconfig` entry is a **provider-owned opaque envelope** —
`store.py` never inspects or validates provider-specific fields, only routes
by the `provider` tag:

```json
{
  "schema_version": 1,
  "entries": {
    "OPENAI_API_KEY": {
      "provider": "oci",
      "ciphertext": "<base64>",
      "metadata": { "key_id": "...", "key_version": "..." }
    }
  }
}
```

- `schema_version` is a top-level field on the *file*, independent of any
  provider's `metadata` shape. V1 records this version but does not perform
  whole-file or provider-envelope schema validation; providers remain the
  authority for their own opaque envelopes. Future releases may use it for
  explicit migration or compatibility handling.
- `metadata` is a free-form dict whose shape is entirely up to the provider
  that wrote it (OCI: `key_id`/`key_version`; AWS: `key_arn`; GCP: `key_name`;
  Azure: `key_id`/`key_version`). Centralizing a typed schema per provider in
  core was rejected — it would mean every new provider, including
  third-party ones, requires a core code change, defeating the plugin model.
- `appconfig` never stores KMS configuration. OCI settings are held only in
  the project-local `.agentsafe/config` file; this keeps a ciphertext store
  independent of KMS configuration and permits it to be created lazily on
  the first `set` operation.
- The `.env` store (see "`.env` support") uses the same `EncryptedBlob` and
  the same `.agentsafe/config` KMS settings; only the on-disk shape differs
  (dotenv `KEY="agentsafe:v1:<base64>"` lines instead of a JSON document).

## Architecture

Target package layout (`src/` layout):

```
agentsafe/
  __init__.py       # public SDK surface: AgentSafe class
  config.py         # resolves agentsafe's own settings: profile, crypto endpoint, key ID, kms provider
  store.py          # appconfig file: JSON schema, atomic write (temp file + os.replace), advisory file lock
  envstore.py       # .env / .env.agent files: dotenv schema, atomic write, advisory file lock (sibling to store.py)
  sdk.py            # AgentSafe class: init(), set(key, value), get(key), remove(key), list_keys()
  env.py            # module-level `.env` API: load(), get(), set(), remove(), list_keys(), encrypt()
  cli.py            # Typer CLI: init, config, set/store, get/retrieve, remove/rm, list, env {encrypt,set,get,remove,list}
  exceptions.py     # AgentSafeError hierarchy
  kms/
    __init__.py     # entry-point discovery + factory: get_provider(name) -> KMSProvider
    base.py         # KMSProvider Protocol + EncryptedBlob type
    oci_provider.py # OCI KMS implementation (oci.key_management + oci.kms_crypto), extra: agentconfigsafe[oci]
tests/
  test_kms_contract.py  # fake in-memory KMSProvider; exercises store.py/sdk.py/cli.py logic, no real crypto
  test_kms_oci.py       # unittest.mock.patch on the oci client; verifies request/response mapping only
  test_store.py         # appconfig schema/round-trip, concurrency/locking
  test_envstore.py      # .env/.env.agent schema/round-trip, concurrency/locking (mirrors test_store.py)
  test_env.py           # env module: load()/get()/set()/remove()/list_keys()/encrypt(), fake KMSProvider
  test_sdk.py
  test_cli.py
pyproject.toml
```

Data flow for a `get`:
`SDK/CLI call` → `store.py` reads `appconfig` and finds the entry for the key →
`kms/__init__.py` resolves the entry's `provider` tag to a `KMSProvider`
(loading its entry point lazily) → `provider.decrypt(blob)` calls the
backend's decrypt API using that provider's own credentials/endpoint →
plaintext returned to the caller only, never written back to disk or logged.
The `.env` store follows the identical flow through `envstore.py`/`env.py`
instead of `store.py`/`sdk.py`.

## Settings & file locations

- **`.agentsafe/config`** (INI-style, **project-local**, cwd-based — e.g.
  `./.agentsafe/config`) — replaces the earlier home-directory
  `~/.agentsafe/config` registry. `init` creates a single flat `[agentsafe]`
  section containing `kms_provider`, `profile`, `crypto_endpoint`, `key_id`,
  and future provider settings. `init` fails only if this file already
  exists; there is no home-directory fallback and no named-application
  indirection — one project directory has exactly one implicit KMS profile.
  (This replaces the named-application/`--application` model from the
  previous design; see the note under "Status" above.) There is
  deliberately no compartment setting — OCI's Encrypt/Decrypt API doesn't
  take one (see "Core concepts").
- **Why project-local, and why this is safe to commit to git.** `profile`,
  `crypto_endpoint`, and `key_id` are identifiers, not secrets — OCI's own
  security model assumes an OCID or endpoint URL grants
  no access without a correctly-scoped IAM policy and valid local
  credentials, the same reasoning that already lets `appconfig`'s ciphertext
  envelopes reference a `key_id` in the clear. Committing `.agentsafe/config`
  alongside `appconfig`/`.env` means a fresh clone has everything needed to
  decrypt except each developer's own local OCI credentials — nothing
  sensitive crosses git.
- **`profile` is the one field that legitimately varies per developer** —
  it names a profile in that developer's own `~/.oci/config`, which is
  never committed. A developer whose local OCI CLI profile is named
  differently from what's committed overrides it with `AGENTSAFE_PROFILE`
  (explicit/env values still win over the file — see resolution order
  below); this needs no special-case code, since it falls out of the
  existing precedence rules.
- **`appconfig` and `.env`/`.env.agent` are per-project, cwd-based**
  (e.g. `./appconfig`, `./.env.agent`, `./.env`) — every project keeps its
  own ciphertext secret set(s), resolved against that same project's
  `.agentsafe/config`.

Settings resolution order (first match wins):
1. Explicit constructor/CLI arguments
2. Environment variables: `AGENTSAFE_KMS_PROVIDER`, `AGENTSAFE_PROFILE`, `AGENTSAFE_CRYPTO_ENDPOINT`, `AGENTSAFE_KEY_ID`
3. The project-local `.agentsafe/config` file's `[agentsafe]` section
4. For `kms_provider` only, select `oci` when it remains unspecified.
   For every other required setting, raise a clear `ConfigError` — never
   silently fall back to defaults for security-relevant settings.

## SDK usage (target shape)

```python
from agentsafe import AgentSafe

safe = AgentSafe(
    kms_provider="oci",  # selected by default when omitted
    profile="DEFAULT",
    crypto_endpoint="https://<vault>-crypto.kms.<region>.oraclecloud.com",
    key_id="ocid1.key.oc1..<key-ocid>",
)

safe.set("OPENAI_API_KEY", "sk-...")  # value: str only (see "Value types")
value = safe.get("OPENAI_API_KEY")  # raises KeyNotFoundError if absent
safe.remove("OPENAI_API_KEY")
```

`profile`/`crypto_endpoint`/`key_id` are OCI-provider settings; other
providers take their own equivalent kwargs (e.g. AWS: `region`, `key_arn`).
`AgentSafe.__init__` forwards whatever settings are relevant to
`kms.get_provider(kms_provider, **settings)` rather than hardcoding OCI's
argument names into the public SDK surface.

**Value types: strings only.** `set(key, value)` requires `value: str`.
Structured secrets (JSON blobs, etc.) are the caller's responsibility to
serialize first. This matches the primary use case (API keys, tokens,
connection strings) and avoids a serialization-format decision and CLI
argument-parsing question that arbitrary JSON values would force.

**Config names: arbitrary non-empty strings.** `set`, `get`, and `remove`
accept any non-empty string as a key name; names need not be valid environment
variable identifiers.

**Missing key: raise, don't return `None`.** `get()` on an absent key raises
`KeyNotFoundError`. A silent `None` for a missing secret is exactly the kind
of thing that turns into a confusing downstream failure (e.g. an agent
calling an API with `api_key=None`) instead of a clear error where the
problem actually is.

## CLI usage (target shape)

Built with **Typer** (type-hint-driven, built on Click so hidden-input
prompts etc. are still available; fits a type-hint-first codebase with less
boilerplate than raw Click).

```
agentsafe init   --profile DEFAULT --crypto-endpoint <url> --key-id <ocid>
agentsafe config                         # display project KMS settings; no KMS calls
agentsafe set    OPENAI_API_KEY [VALUE]   # prompts (hidden input), or reads stdin, if VALUE omitted
agentsafe get    OPENAI_API_KEY
agentsafe remove OPENAI_API_KEY
agentsafe list                            # key names only — see below
```

`set`, `get`, `remove`, and `list` accept `--path <file>` to select the
`appconfig` file location (default: `./appconfig`), matching the SDK's
settings resolution order.

`init` writes the resolved settings to the project-local `.agentsafe/config`
file. It never reads, creates, or overwrites `appconfig`; the ciphertext
store is created lazily by the first `set`. `init` fails only if
`.agentsafe/config` already exists. It does not create cloud resources
(vault, key, compartment) — those are assumed to already exist and be
reachable via the given profile/credentials.

`config` displays the raw `[agentsafe]` settings from the project-local
`.agentsafe/config` file in a stable key order. It never contacts KMS or
decrypts values; this configuration contains only provider identifiers, not
plaintext secrets or credentials. `config --path <file>` displays an alternate
configuration file.

**`list` shows key names only, never decrypted values.** It does not call
Decrypt at all — fast, and it never puts plaintext secrets on a
terminal/screen-recording/CI log just because someone wanted to see what's
configured.

## `.env` support

A second, parallel store — same `EncryptedBlob`/`KMSProvider` machinery and
the same project-local `.agentsafe/config` KMS settings as `appconfig`, but
dotenv-shaped instead of JSON, for teams whose other tooling (frameworks,
`docker compose`, CI systems) already auto-loads a `.env` file. Workflow
shape is adapted from the `envrypt` PyPI package; the encryption itself is
not — see the note under "Status".

- **`.env.agent`** (project-local, cwd-based, e.g. `./.env.agent`) — a
  plaintext `KEY=value` file the developer edits locally. This is a
  deliberate, sanctioned exception to "plaintext never written to disk": it
  is the one place a developer types a real secret in the clear, exactly
  as they would at a hidden CLI prompt. **It must never be committed** —
  `agentsafe env encrypt` warns (but does not block) if it isn't listed in
  the project's `.gitignore`.
- **`.env`** (project-local, cwd-based, e.g. `./.env`) — the compiled,
  fully-encrypted, git-committable output. Every value is encrypted
  unconditionally; there is no `envrypt`-style naming-convention exception
  that leaves some values in plaintext. Each line is
  `KEY="agentsafe:v1:<base64 of the JSON EncryptedBlob mapping>"` — a
  syntactically valid, quoted dotenv value so non-agentsafe dotenv tooling
  can still parse the file (it just can't decrypt it). The `agentsafe:v1:`
  prefix mirrors `appconfig`'s `schema_version`, scoped per-line since
  there's no single top-level document here to version.
- **`.env` key names must be valid environment-variable identifiers**
  (unlike `appconfig`'s arbitrary non-empty strings) — they round-trip
  through `os.environ` via `env.load()`, which most platforms/shells
  restrict to letters, digits, and underscores, not starting with a digit.
- **`agentsafe env encrypt`** (CLI) / **`env.encrypt()`** (SDK) fully
  regenerates `.env` from `.env.agent` — `.env` is a derived artifact, never
  hand-edited, matching `envrypt`'s own `encrypt > .env` full-redirect
  semantics. `.env.agent`'s existing entries are the single source of truth
  for this operation.
- **SDK (`from agentsafe import env`)**, mirroring `envrypt`'s own
  `from envrypt import env; env.get(...)` shape:
  ```python
  from agentsafe import env

  env.load()                     # decrypt every entry in .env, populate os.environ
  value = env.get("OPENAI_API_KEY")   # decrypt one value without touching os.environ
  env.set("OPENAI_API_KEY", "sk-...")  # encrypt+write one entry directly into .env
  env.remove("OPENAI_API_KEY")
  env.list_keys()                # names only, never decrypts — same as AgentSafe.list_keys()
  env.encrypt()                  # compile .env.agent -> .env (see above)
  ```
  `env.load()` populating `os.environ` with plaintext is the other
  sanctioned in-memory-plaintext exception (see "Security requirements");
  it is scoped to the process's lifetime, same as any 12-factor-app secret,
  and is never written back to disk.
- **CLI**: `agentsafe env encrypt`, `agentsafe env set KEY [VALUE]`,
  `agentsafe env get KEY`, `agentsafe env remove KEY`, `agentsafe env list`
  — deliberately no bulk "decrypt everything to stdout" command, for the
  same reason `list` never decrypts; an application consumes decrypted
  values via `env.load()`/`env.get()` in-process, not by piping a CLI dump.
- Same atomic-write (temp file + `os.replace()`) and advisory-lock
  discipline as `appconfig` and `.agentsafe/config` applies to `.env`
  writes (see "Concurrency & durability").

## Security requirements (non-negotiable for any change)

- Plaintext values must never be written to disk, logs, shell history files,
  or exception messages/tracebacks. There are exactly two sanctioned,
  deliberate exceptions, both documented in "`.env` support": the developer
  hand-edits `.env.agent` locally (never committed, warned about if
  ungitignored), and `env.load()` populates `os.environ` in-process for the
  running application's lifetime. Neither is written back to disk by
  agentsafe.
- `appconfig` and `.env` contain ciphertext envelopes and metadata only —
  never plaintext secret values, KMS configuration, raw key material,
  private keys, or auth tokens.
- Decryption happens only in memory at the moment the SDK/CLI caller requests
  a value (or, for `env.load()`, at the moment it populates `os.environ`);
  do not otherwise cache decrypted plaintext beyond that call's return.
- Key material and key versions live only in the KMS backend (whichever
  provider is configured); `agentsafe` stores only identifiers (key
  OCID/ARN/resource name, vault/endpoint), never key bytes, regardless of
  provider.
- `set`/`store` should support a hidden-input prompt or stdin piping as an
  alternative to a bare CLI argument, since arguments are visible via `ps`
  and shell history — document this tradeoff wherever the argument form is
  offered.
- Never swallow a KMS provider's authentication/authorization errors — wrap
  them in a typed `KMSError`/`ConfigError` using exception chaining, retaining
  the original provider exception as the cause. Do not fall back to an
  insecure path. This applies uniformly across providers, not just OCI.
- `list` and `env list` never decrypt (see CLI usage above and "`.env`
  support").
- Provider name collisions are a hard error, never silently resolved (see
  plugin architecture above).
- `.agentsafe/config`, `appconfig`, `.env`, the temporary files used to
  replace each of them, and their lock files must be created
  owner-readable/writable only (mode `0600`) where the operating system
  supports POSIX file permissions. `.env.agent` is the developer's own
  plaintext file and is not agentsafe-managed in this sense, but `agentsafe
  env encrypt` still warns if it isn't gitignored.

## Out of scope for v1 (deliberately deferred)

- **Key rotation / re-encryption.** No `agentsafe rotate` command. Decrypt
  already works regardless of which key version encrypted a given entry (as
  long as that version isn't disabled/deleted), so this is a hygiene
  improvement to add later once there's real usage to inform the design, not
  a correctness blocker now.

Three items previously listed here are no longer applicable: compartment
name/OCID resolution doesn't apply because compartment isn't an agentsafe
setting at all anymore — it was never used by the OCI Encrypt/Decrypt calls
agentsafe makes (see "Core concepts"), so it was removed rather than kept as
an OCID-only setting. Bulk `.env`
import/export is now in scope via the `.env`/`.env.agent` store (see
"`.env` support") — the original concern (a plaintext `.env` source file is
exactly what agentsafe exists to replace) is addressed because only
`.env.agent`, a deliberate and gitignored exception, ever holds plaintext;
the committed `.env` is always fully encrypted. A project-local KMS settings
file is now the *only* location (see "Settings & file locations") — the
named-application/home-directory registry it replaces is gone, not merely
supplemented.

## Concurrency & durability

- **Atomic writes**: `appconfig` (in `store.py`), `.env`/`.env.agent` (in
  `envstore.py`), and `.agentsafe/config` (in `config.py`) are all written
  to a temp file, then `os.replace()` — none of them is ever left
  half-written even on a crash mid-write.
- **Advisory file lock** (e.g. the `filelock` library) held across the full
  read-modify-write cycle of any `appconfig`/`.env` `set`/`remove`,
  `.env` `encrypt`, or `.agentsafe/config` `init`, so two concurrent CLI/SDK
  writers (e.g. a CLI `set` racing an SDK write from a running app) can't
  silently clobber each other's change.

## Dependencies (expected)

- `oci` — the OCI Python SDK (`oci.key_management` + `oci.kms_crypto`). Used
  by `kms/oci_provider.py` only, behind the `agentconfigsafe[oci]` extra.
- Future provider SDKs are added as optional extras only when their providers
  are implemented (for example, `boto3` for AWS).
- `typer` — CLI framework.
- `filelock` — advisory locking for `appconfig`, `.env`/`.env.agent`, and
  `.agentsafe/config` writes.
- `python-dotenv` — parses `.env.agent`/`.env` (comments, quoting, escaping)
  in `envstore.py`; a core dependency, not an extra, since it's a small,
  pure-Python, dependency-free package and `.env` support is a first-class
  feature rather than a cloud-provider plugin. Chosen over hand-rolling a
  parser so `.env`/`.env.agent` behave exactly like the dotenv files other
  tooling already expects, and because `envrypt` (the workflow reference for
  this feature) is itself built on it.
- No custom cryptography implementation — all encrypt/decrypt is delegated to
  the configured KMS provider.
- PyPI distribution name **`agentconfigsafe`**; the Python import package and
  CLI command remain **`agentsafe`**.
- **Python 3.10+** — modern `X | Y` union hints without `__future__` imports,
  and the clean keyword-arg form of `importlib.metadata.entry_points(group=...)`.

## Distribution & releases

- The PyPI distribution name is **`agentconfigsafe`**; the import package and
  CLI command are **`agentsafe`**. Install OCI support with
  `pip install "agentconfigsafe[oci]"`.
- Package metadata in `pyproject.toml` is the release source of truth: it
  declares the MIT license, supported Python classifiers, and the GitHub
  homepage, repository, and issue-tracker URLs.
- `.github/workflows/release.yml` builds and validates the distribution when a
  GitHub release is published, then publishes through PyPI trusted publishing
  in the `pypi` GitHub environment. Do not add long-lived PyPI API tokens to
  the repository or workflow.

## Dev commands

Fill these in as the project is scaffolded; keep this section accurate.

- Install (editable, with dev deps): `pip install -e ".[dev]"`
- Run tests: `pytest`
- Lint/format: `ruff check .` and `ruff format .`
- Type-check: `mypy src/agentsafe`

## Conventions

- Type hints on all public functions/methods; docstrings on the public SDK
  surface (`AgentSafe` and its methods, and the `env` module's functions).
- Raise typed exceptions from `agentsafe.exceptions` (`KeyNotFoundError`,
  `KMSError`, `ConfigError`, ...) rather than bare `Exception`/`ValueError`.
- **Test the provider-agnostic logic once, against the `KMSProvider`
  contract** (`test_kms_contract.py`), using a trivial fake in-memory
  provider — no real crypto, no cloud-specific mocking library. Each
  concrete provider then gets its own thin test file that only verifies it
  maps correctly to/from its cloud SDK's request/response shape
  (`unittest.mock.patch` on that SDK's client — no `moto` or other
  provider-specific mocking framework needed). `test_env.py` follows the
  same fake-provider convention rather than introducing a second one.
- Reserve real KMS calls for a separate integration test suite gated behind
  an explicit marker/env var (e.g. `AGENTSAFE_RUN_INTEGRATION=1`), since
  those require live cloud credentials and a real vault/key.
- Keep `store.py`/`envstore.py` (file formats) and `kms/` (provider calls)
  decoupled from `sdk.py`/`env.py`/`cli.py` (user-facing surface) so either
  can be tested and evolved independently.
