#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

from ageos.integrations.openai_shim import AgeosOpenAI


def main() -> int:
    specialty = os.environ.get("AGEOS_SPECIALITY", "default-instruct")
    niceness = int(os.environ.get("AGEOS_NICENESS", "0"))

    print("AgeOS basic agent starting")
    print(f"agent_id={os.environ.get('AGEOS_AGENT_ID', 'not-set')}")
    print(f"sandbox={os.environ.get('AGEOS_SANDBOX', '0')}")
    print(f"specialty={specialty}")
    print(f"niceness={niceness}")

    client = AgeosOpenAI(speciality=specialty, niceness=niceness)
    response = client.chat.completions.create(
        model="ageos-local",
        messages=[
            {
                "role": "user",
                "content": (
                    "Reply with one short sentence confirming the AgeOS basic "
                    "agent can reach the local model."
                ),
            }
        ],
    )

    answer = response.choices[0].message.content.strip()
    print("model_response:")
    print(answer)
    print("AgeOS basic agent finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
