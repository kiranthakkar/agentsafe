"""Store and retrieve one demonstration value with agentsafe.

Run ``agentsafe init`` first, as described in this directory's README. The
default value is intentionally non-sensitive and is printed only to validate
the round trip; never use this pattern to print a real production secret.
"""

import os
from pathlib import Path

from agentsafe import AgentSafe

APPLICATION = "demo"
APPCONFIG_PATH = Path(__file__).parent / "appconfig"
DEMO_KEY = "DEMO_SECRET"
DEMO_VALUE = os.environ.get("AGENTSAFE_DEMO_SECRET", "demo-value-not-a-real-secret")


def main() -> None:
    """Encrypt a demonstration value, then decrypt it to validate the setup."""
    safe = AgentSafe(APPCONFIG_PATH, application=APPLICATION)
    safe.set(DEMO_KEY, DEMO_VALUE)
    retrieved_value = safe.get(DEMO_KEY)

    if retrieved_value != DEMO_VALUE:
        raise RuntimeError("agentsafe validation failed: retrieved value did not match")

    print(f"Validation succeeded. Retrieved {DEMO_KEY}: {retrieved_value}")


if __name__ == "__main__":
    main()
