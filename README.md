# agentsafe

`agentsafe` stores encrypted configuration values in a project-local `appconfig`
file. Encryption and decryption are performed by a customer-managed OCI KMS key;
the file never contains plaintext or key material.

```console
agentsafe init --profile DEFAULT --compartment <compartment-ocid> \
  --crypto-endpoint <vault-crypto-url> --key-id <key-ocid>
agentsafe set OPENAI_API_KEY
agentsafe get OPENAI_API_KEY
```

`agentsafe set NAME VALUE` is available for automation, but command-line
arguments can be exposed in shell history and process listings. Prefer the
hidden prompt (omit `VALUE`) or pipe the value to standard input.

## Python SDK

Install the OCI provider extra in the application environment:

```console
python -m pip install "agentconfigsafe[oci]"
```

Configure the KMS settings once with `agentsafe init` (shown above), or supply
them directly when constructing `AgentSafe`. The default store is `appconfig`
in the process's current directory; pass an explicit path when the application
does not run from its project directory.

```python
from pathlib import Path

from agentsafe import AgentSafe, KeyNotFoundError

safe = AgentSafe(
    Path("/srv/my-service/appconfig"),
    profile="DEFAULT",
    compartment="ocid1.compartment.oc1..example",
    crypto_endpoint="https://example-crypto.kms.us-phoenix-1.oraclecloud.com",
    key_id="ocid1.key.oc1..example",
)

try:
    api_key = safe.get("OPENAI_API_KEY")
except KeyNotFoundError:
    # Configure the secret before starting the application.
    raise RuntimeError("OPENAI_API_KEY has not been configured") from None

# Pass ``api_key`` directly to your API client; do not log it or write it to disk.
```

Settings resolve in this order: constructor arguments, `AGENTSAFE_*`
environment variables, then `~/.agentsafe/config`. The KMS provider defaults
to OCI; the OCI profile, compartment OCID, crypto endpoint, and key OCID must
all be configured. `get()` decrypts only for the duration of the call;
`list_keys()` returns names without decrypting values.

The PyPI distribution is named `agentconfigsafe`; the Python import and CLI
remain `agentsafe`.
