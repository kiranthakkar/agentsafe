# agentsafe

Agent Safe `agentsafe` is a Python library and CLI for storing application configuration
values—API keys, access tokens, passwords, and connection strings—as KMS-backed
ciphertext. It never generates, stores, or manages encryption key material.
Every encryption and decryption operation is delegated to a customer-managed
Oracle Cloud Infrastructure (OCI) KMS key.

The PyPI distribution is named `agentconfigsafe`; Python imports and the CLI
are named `agentsafe`.

## Why use it?

Applications often need sensitive configuration but should not keep it in
source control, plaintext `.env` files, or application configuration files.
`agentsafe` keeps encrypted values in a project-local `appconfig` file while
leaving encryption authority with the customer’s OCI KMS key and IAM policies.

Common uses include:

- API keys for LLM, SaaS, or third-party integrations used by AI agents.
- Database connection strings, webhook secrets, and service credentials.
- Separate KMS settings for development, billing, analytics, or other
  applications on the same machine.
- Setup scripts that configure a secret once, followed by runtime SDK reads.

## Security model

- Plaintext values are encrypted through OCI KMS before they reach `appconfig`.
- `appconfig` contains ciphertext envelopes and provider metadata only; it
  never contains plaintext values, OCI credentials, or key material.
- OCI KMS configuration is stored separately in named sections of
  `~/.agentsafe/config`, not in `appconfig`.
- `get()` decrypts in memory only for the duration of the call. Values are not
  cached by `agentsafe`.
- `list` returns names only and never calls KMS Decrypt.
- `agentsafe` relies on OCI’s standard profile configuration and IAM. It does
  not implement a second authentication system.

Avoid placing real secrets directly in shell arguments: they can be exposed in
shell history and process listings. Prefer the hidden `set` prompt or a
carefully controlled standard-input workflow.

## Install

Install the OCI provider extra in the application environment:

```console
python -m pip install "agentconfigsafe[oci]"
```

You also need an OCI profile in `~/.oci/config`, a vault crypto endpoint, and
a KMS key that the profile is allowed to use for Encrypt and Decrypt.

## Quick start: CLI

Create a named application profile. This writes OCI identifiers and profile
settings to `~/.agentsafe/config`; it does not create or modify `appconfig`.

```console
agentsafe init --application billing --profile DEFAULT \
  --compartment <compartment-ocid> \
  --crypto-endpoint https://<vault>-crypto.kms.<region>.oraclecloud.com \
  --key-id <key-ocid>
```

Store a value. Omitting the value opens a hidden prompt; the first `set`
creates the local `appconfig` ciphertext store.

```console
agentsafe set OPENAI_API_KEY
agentsafe get OPENAI_API_KEY
agentsafe list
agentsafe remove OPENAI_API_KEY
```

Use `--path /path/to/appconfig` with `set`, `get`, `list`, or `remove` when an
application’s ciphertext store is not in the current directory.

## Multiple applications

Each `init --application <name>` call adds a separate section such as
`[application:billing]` to `~/.agentsafe/config`. This permits independent OCI
profiles, compartments, vault crypto endpoints, and key OCIDs for different
applications.

```console
agentsafe init --application billing --profile BILLING_PROFILE ...
agentsafe init --application analytics --profile ANALYTICS_PROFILE ...
```

Select the intended application from Python with `application="billing"`, or
set `AGENTSAFE_APPLICATION=billing` for a process.

## Python SDK

After initializing a named profile, use it from an application:

```python
from pathlib import Path

from agentsafe import AgentSafe, KeyNotFoundError

safe = AgentSafe(
    Path("/srv/billing/appconfig"),
    application="billing",
)

try:
    api_key = safe.get("OPENAI_API_KEY")
except KeyNotFoundError:
    raise RuntimeError("OPENAI_API_KEY has not been configured") from None

# Pass api_key directly to the consuming client. Do not log or persist it.
```

For initial provisioning from Python, register the profile first:

```python
from agentsafe import AgentSafe

AgentSafe.init(
    application="billing",
    profile="DEFAULT",
    compartment="ocid1.compartment.oc1..example",
    crypto_endpoint="https://example-crypto.kms.us-phoenix-1.oraclecloud.com",
    key_id="ocid1.key.oc1..example",
)
```

Settings resolve in this order: explicit SDK/CLI arguments, `AGENTSAFE_*`
environment variables, the selected named application profile in
`~/.agentsafe/config`, then a legacy global fallback section. OCI is the
default provider; OCI requires a profile, compartment OCID, crypto endpoint,
and key OCID.

## Example

See [examples/README.md](examples/README.md) for a runnable example that
initializes a `demo` profile, stores a non-sensitive validation value, and
reads it back through OCI KMS.

## Current scope

OCI KMS is the bundled provider in this release. The provider architecture uses
Python entry points so additional customer-managed KMS backends can be added
without changing the storage or SDK layers. Key rotation, bulk import/export,
and cloud resource creation are intentionally outside the current scope.
