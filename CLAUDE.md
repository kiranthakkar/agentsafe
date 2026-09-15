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
(see "KMS provider plugin architecture"). Encrypted values are persisted to a
local file named `appconfig`.

Agent developers use `agentsafe` two ways:
- **CLI** — `init`, `set`/`store`, `get`/`retrieve`, `remove` config parameters
  from a terminal or setup script.
- **SDK** — import `agentsafe` in a Python application to fetch decrypted
  config values at runtime.

> Status: this repo is currently empty. This file is both the working
> architecture guide and the spec to scaffold against. All decisions below
> were made deliberately (see rationale inline) — update this doc, don't
> silently drift from it, if a decision changes during implementation.

## Core concepts

- **KMS-backed encryption, no local keys.** `agentsafe` calls the configured
  provider's Encrypt/Decrypt API for every operation. It stores key/vault
  identifiers, never key material.
- **`appconfig` file.** The on-disk artifact holding each application's
  encrypted parameters — a **JSON** document mapping config names to
  provider-tagged ciphertext envelopes (see schema below). KMS configuration
  lives only in `~/.agentsafe/config`. No plaintext secret value is ever
  written into this file. Chosen over YAML/TOML because it needs no extra
  dependency and the file is machine-written/machine-read only.
- **OCI profile-based auth (for the OCI provider).** Relies on the standard
  OCI SDK/CLI config file (`~/.oci/config`) and profiles — `agentsafe` does
  not implement its own auth. Each provider owns its own auth mechanism (see
  below); "profile" is an OCI-specific concept, not a cross-provider one.
- **Four required OCI settings**, independently configurable by the end
  user (not hardcoded): **profile name**, **KMS compartment OCID** (OCID
  only for v1 — no name-to-OCID resolution; see rationale below), **KMS vault
  crypto endpoint** (the per-vault URL used for Encrypt/Decrypt, distinct
  from the KMS management endpoint), and **KMS key OCID**. The key OCID is
  required for Encrypt; it is also recorded in each OCI ciphertext envelope
  so the correct key can be used for Decrypt.
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
- **Each provider owns its own auth/config.** OCI: profile + compartment +
  crypto endpoint + key OCID. AWS: profile/region + key ARN. GCP: service account/ADC +
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
- `appconfig` never stores KMS configuration. OCI settings are held only in the
  named application sections of `~/.agentsafe/config`; this keeps a ciphertext
  store independent of KMS configuration and permits it to be created lazily
  on the first `set` operation.
- `application` is a required non-empty name supplied to `init`. It identifies
  the matching named configuration in `~/.agentsafe/config`; later SDK/CLI
  calls select that profile using the same argument or `AGENTSAFE_APPLICATION`.

## Architecture

Target package layout (`src/` layout):

```
agentsafe/
  __init__.py       # public SDK surface: AgentSafe class + convenience functions
  config.py         # resolves agentsafe's own settings: profile, compartment, crypto endpoint, kms provider
  store.py          # appconfig file: JSON schema, atomic write (temp file + os.replace), advisory file lock
  sdk.py            # AgentSafe class: init(), set(key, value), get(key), remove(key), list_keys()
  cli.py            # Typer CLI: init, set/store, get/retrieve, remove/rm, list
  exceptions.py     # AgentSafeError hierarchy
  kms/
    __init__.py     # entry-point discovery + factory: get_provider(name) -> KMSProvider
    base.py         # KMSProvider Protocol + EncryptedBlob type
    oci_provider.py # OCI KMS implementation (oci.key_management + oci.kms_crypto), extra: agentconfigsafe[oci]
tests/
  test_kms_contract.py  # fake in-memory KMSProvider; exercises store.py/sdk.py/cli.py logic, no real crypto
  test_kms_oci.py       # unittest.mock.patch on the oci client; verifies request/response mapping only
  test_store.py         # appconfig schema/round-trip, concurrency/locking
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

## Settings & file locations

- **`~/.agentsafe/config`** (INI-style) — a named application configuration
  registry. `init --application billing` creates an `[application:billing]`
  section containing `application`, `kms_provider`, `profile`, `compartment`,
  `crypto_endpoint`, `key_id`, and future provider settings. Multiple sections
  let one customer create independent `AgentSafe` instances for many
  applications. The legacy `[agentsafe]` section remains an optional fallback.
- **Application-local KMS settings are supported in v1.** Each project stores
  its selected provider and provider settings in its own `appconfig`. A
  customer may therefore use different OCI profiles, compartments, crypto
  endpoints, and key OCIDs across applications on the same machine.
- **`appconfig` is per-project, cwd-based** (e.g. `./appconfig`) — every
  project keeps its own ciphertext secret set. KMS configuration is selected
  from the named application registry in `~/.agentsafe/config`.

Settings resolution order (first match wins):
1. Explicit constructor/CLI arguments (including `application`)
2. Environment variables: `AGENTSAFE_APPLICATION`, `AGENTSAFE_KMS_PROVIDER`, `AGENTSAFE_PROFILE`, `AGENTSAFE_COMPARTMENT`, `AGENTSAFE_CRYPTO_ENDPOINT`, `AGENTSAFE_KEY_ID`
3. The selected named `[application:<application>]` section in `~/.agentsafe/config`
4. The legacy `[agentsafe]` global fallback section
5. For `kms_provider` only, select `oci` when it remains unspecified.
   For every other required setting, raise a clear `ConfigError` — never
   silently fall back to defaults for security-relevant settings.

## SDK usage (target shape)

```python
from agentsafe import AgentSafe

safe = AgentSafe(
    kms_provider="oci",  # selected by default when omitted
    application="billing",  # selects [application:billing]
    profile="DEFAULT",
    compartment="ocid1.compartment.oc1..xxxx",  # OCID only, no name resolution (see below)
    crypto_endpoint="https://<vault>-crypto.kms.<region>.oraclecloud.com",
    key_id="ocid1.key.oc1..<key-ocid>",
)

safe.set("OPENAI_API_KEY", "sk-...")  # value: str only (see "Value types")
value = safe.get("OPENAI_API_KEY")  # raises KeyNotFoundError if absent
safe.remove("OPENAI_API_KEY")
```

`profile`/`compartment`/`crypto_endpoint`/`key_id` are OCI-provider settings; other
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

**Compartment: OCID only, no name resolution in v1.** Resolving a friendly
name would need an extra `oci.identity` `list_compartments` call, IAM
permissions the caller might not have, and is ambiguous across nested
compartments. The OCID is what the Encrypt/Decrypt calls need anyway, and
it's a one-time copy from the OCI console during `init`.

## CLI usage (target shape)

Built with **Typer** (type-hint-driven, built on Click so hidden-input
prompts etc. are still available; fits a type-hint-first codebase with less
boilerplate than raw Click).

```
agentsafe init   --application billing --profile DEFAULT --compartment <ocid> --crypto-endpoint <url> --key-id <ocid>
agentsafe set    OPENAI_API_KEY [VALUE]   # prompts (hidden input) if VALUE omitted
agentsafe get    OPENAI_API_KEY
agentsafe remove OPENAI_API_KEY
agentsafe list                            # key names only — see below
```

`init` requires `--application` and writes the resolved settings only to its
named `[application:<name>]` section in `~/.agentsafe/config`. It never reads,
creates, or overwrites `appconfig`; the ciphertext store is created lazily by
the first `set`. `init` fails only if that named application configuration
already exists. It does not create cloud
resources (vault, key, compartment) — those are assumed to already exist and
be reachable via the given profile/credentials.

**`list` shows key names only, never decrypted values.** It does not call
Decrypt at all — fast, and it never puts plaintext secrets on a
terminal/screen-recording/CI log just because someone wanted to see what's
configured.

## Security requirements (non-negotiable for any change)

- Plaintext values must never be written to disk, logs, shell history files,
  or exception messages/tracebacks.
- `appconfig` contains ciphertext envelopes and metadata only — never plaintext
  secret values, KMS configuration, raw key material, private keys, or auth
  tokens.
- Decryption happens only in memory at the moment the SDK/CLI caller requests
  a value; do not cache decrypted plaintext beyond that call's return.
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
- `list` never decrypts (see CLI usage above).
- Provider name collisions are a hard error, never silently resolved (see
  plugin architecture above).
- `~/.agentsafe/config`, `appconfig`, temporary files used to replace
  `appconfig`, and lock files must be created owner-readable/writable only
  (mode `0600`) where the operating system supports POSIX file permissions.

## Out of scope for v1 (deliberately deferred)

- **Key rotation / re-encryption.** No `agentsafe rotate` command. Decrypt
  already works regardless of which key version encrypted a given entry (as
  long as that version isn't disabled/deleted), so this is a hygiene
  improvement to add later once there's real usage to inform the design, not
  a correctness blocker now.
- **Bulk import/export** (e.g. `.env` file import, bulk env-var export).
  Single-key `set`/`get`/`remove` covers the core use case; bulk import also
  raises its own security UX question (a plaintext `.env` source file is
  exactly what agentsafe exists to replace) that shouldn't block v1.
- **Compartment name → OCID resolution.** OCID only for now (see SDK usage
  section).
- **Project-local settings file.** Global `~/.agentsafe/config` plus env
  vars/CLI flags only (see "Settings & file locations").

## Concurrency & durability

- **Atomic writes**: write to a temp file, then `os.replace()` — never leave
  `appconfig` half-written even on a crash mid-write.
- **Advisory file lock** (e.g. the `filelock` library) held across the full
  read-modify-write cycle of any `set`/`remove`, so two concurrent CLI/SDK
  writers (e.g. a CLI `set` racing an SDK write from a running app) can't
  silently clobber each other's change.

## Dependencies (expected)

- `oci` — the OCI Python SDK (`oci.key_management` + `oci.kms_crypto`). Used
  by `kms/oci_provider.py` only, behind the `agentconfigsafe[oci]` extra.
- Future provider SDKs are added as optional extras only when their providers
  are implemented (for example, `boto3` for AWS).
- `typer` — CLI framework.
- `filelock` — advisory locking for `appconfig` writes.
- No custom cryptography implementation — all encrypt/decrypt is delegated to
  the configured KMS provider.
- PyPI distribution name **`agentconfigsafe`**; the Python import package and
  CLI command remain **`agentsafe`**.
- **Python 3.10+** — modern `X | Y` union hints without `__future__` imports,
  and the clean keyword-arg form of `importlib.metadata.entry_points(group=...)`.

## Dev commands

Fill these in as the project is scaffolded; keep this section accurate.

- Install (editable, with dev deps): `pip install -e ".[dev]"`
- Run tests: `pytest`
- Lint/format: `ruff check .` and `ruff format .`
- Type-check: `mypy agentsafe`

## Conventions

- Type hints on all public functions/methods; docstrings on the public SDK
  surface (`AgentSafe` and its methods).
- Raise typed exceptions from `agentsafe.exceptions` (`KeyNotFoundError`,
  `KMSError`, `ConfigError`, ...) rather than bare `Exception`/`ValueError`.
- **Test the provider-agnostic logic once, against the `KMSProvider`
  contract** (`test_kms_contract.py`), using a trivial fake in-memory
  provider — no real crypto, no cloud-specific mocking library. Each
  concrete provider then gets its own thin test file that only verifies it
  maps correctly to/from its cloud SDK's request/response shape
  (`unittest.mock.patch` on that SDK's client — no `moto` or other
  provider-specific mocking framework needed).
- Reserve real KMS calls for a separate integration test suite gated behind
  an explicit marker/env var (e.g. `AGENTSAFE_RUN_INTEGRATION=1`), since
  those require live cloud credentials and a real vault/key.
- Keep `store.py` (file format) and `kms/` (provider calls) decoupled from
  `sdk.py`/`cli.py` (user-facing surface) so either can be tested and
  evolved independently.
