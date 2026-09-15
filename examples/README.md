# agentsafe example

This example initializes an OCI-backed `agentsafe` application, encrypts a
demonstration value, then decrypts and prints it to validate the setup.

The printed default value is deliberately non-sensitive. Do not use this
example to print real production secrets.

## Prerequisites

- Python 3.10+
- OCI credentials configured in `~/.oci/config`
- An OCI vault crypto endpoint and a key OCID that the selected profile can
  use for encryption and decryption

Install the package with its OCI provider:

```bash
python -m pip install "agentconfigsafe[oci]"
```

## Initialize the example application

From the repository root, initialize the named `demo` configuration in
`~/.agentsafe/config`:

```bash
agentsafe init --application demo --profile DEFAULT \
  --compartment <compartment-ocid> \
  --crypto-endpoint <vault-crypto-endpoint> \
  --key-id <key-ocid>
```

The first run creates `examples/appconfig`. It contains only encrypted values
and ciphertext metadata; OCI configuration remains in `~/.agentsafe/config`.
The store is ignored by Git.

## Run the Python application

```bash
python examples/store_and_read.py
```

The script stores the non-sensitive value `demo-value-not-a-real-secret` under
`DEMO_SECRET`, reads it back through OCI KMS, and prints it after confirming
the values match.

To use a different *non-production* validation value, set it through the
environment rather than a command-line argument:

```bash
export AGENTSAFE_DEMO_SECRET="my-safe-demo-value"
python examples/store_and_read.py
```

For real applications, use `safe.get("YOUR_SECRET_NAME")` and pass the result
directly to the consuming client. Do not print, log, or persist the plaintext
value.
