# agentsafe examples

This directory has two runnable examples against the same project-local OCI
configuration: one round-trips a value through the JSON `appconfig` store,
the other through the `.env`/`.env.agent` store. Both encrypt a
demonstration value, then decrypt and print it to validate the setup.

The printed default value is deliberately non-sensitive. Do not use either
example to print real production secrets.

## Prerequisites

- Python 3.10+
- OCI credentials configured in `~/.oci/config` (or, when running on OCI,
  an instance/resource principal — use `--auth-type` below)
- An OCI vault crypto endpoint and a key OCID that the selected profile can
  use for encryption and decryption

Install the package with its OCI provider:

```bash
python -m pip install "agentconfigsafe[oci]"
```

## Initialize the project-local configuration

From the repository root, initialize the project-local configuration at
`.agentsafe/config`. Both examples below reuse this same file — there's no
separate `.env`-specific setup step.

```bash
agentsafe init --profile DEFAULT \
  --crypto-endpoint <vault-crypto-endpoint> \
  --key-id <key-ocid>
```

On an OCI instance or in an OCI service, replace `--profile DEFAULT` with
`--auth-type instance_principal` (or `resource_principal`); the examples
themselves need no changes.

The plaintext `examples/.env.agent` and the examples' lock files are ignored
by Git. A consuming project would typically commit `.agentsafe/config`,
`appconfig`, and `.env` — see the main README's "Security model" — but never
`.env.agent`, which always stays plaintext-local.

## Example 1: the `appconfig` (JSON) store

```bash
python examples/store_and_read.py
```

The script stores the non-sensitive value `demo-value-not-a-real-secret` under
`DEMO_SECRET` in `examples/appconfig`, reads it back through OCI KMS, and
prints it after confirming the values match.

To use a different *non-production* validation value, set it through the
environment rather than a command-line argument:

```bash
export AGENTSAFE_DEMO_SECRET="my-safe-demo-value"
python examples/store_and_read.py
```

## Example 2: the `.env` store

```bash
python examples/env_store_and_read.py
```

The script writes `DEMO_SECRET=demo-value-not-a-real-secret` into the
plaintext `examples/.env.agent`, runs the equivalent of `agentsafe env
encrypt` to compile it into a fully-encrypted `examples/.env`, reads
`DEMO_SECRET` back through OCI KMS via `env.get()`, and prints it after
confirming the values match. The same `AGENTSAFE_DEMO_SECRET` environment
variable overrides the value here too.

## For real applications

Use `safe.get("YOUR_SECRET_NAME")` (or `env.get(...)`/`env.load()` for the
`.env` store) and pass the result directly to the consuming client. Do not
print, log, or persist the plaintext value.
