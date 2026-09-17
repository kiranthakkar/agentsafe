"""Store and retrieve one demonstration value via agentsafe's `.env` store.

Run ``agentsafe init`` first, as described in this directory's README — the
same project-local `.agentsafe/config` used by store_and_read.py is reused
here. The default value is intentionally non-sensitive and is printed only
to validate the round trip; never use this pattern to print a real
production secret.
"""

import os
import sys
from pathlib import Path

from agentsafe import env
from agentsafe.exceptions import AgentSafeError

ENV_AGENT_PATH = Path(__file__).parent / ".env.agent"
ENV_PATH = Path(__file__).parent / ".env"
DEMO_KEY = "DEMO_SECRET"
DEMO_VALUE = os.environ.get("AGENTSAFE_DEMO_SECRET", "demo-value-not-a-real-secret")


def main() -> None:
    """Compile .env.agent into .env, then decrypt it to validate the setup."""
    ENV_AGENT_PATH.write_text(f"{DEMO_KEY}={DEMO_VALUE}\n", encoding="utf-8")
    env.encrypt(ENV_AGENT_PATH, ENV_PATH)
    retrieved_value = env.get(DEMO_KEY, ENV_PATH)

    if retrieved_value != DEMO_VALUE:
        raise RuntimeError("agentsafe validation failed: retrieved value did not match")

    print(f"Validation succeeded. Retrieved {DEMO_KEY}: {retrieved_value}")


if __name__ == "__main__":
    try:
        main()
    except AgentSafeError as error:
        print(f"agentsafe error: {error}", file=sys.stderr)
        print("Have you run `agentsafe init` yet? See this directory's README.", file=sys.stderr)
        sys.exit(1)
