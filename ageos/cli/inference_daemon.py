from __future__ import annotations

from ageos.http_api import ApiConfig, run_http_api
from ageos.inference import load_inference_config


def main() -> int:
    config = load_inference_config()
    run_http_api(
        ApiConfig(
            host=config.host,
            port=config.port,
            default_specialty=config.default_specialty,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
