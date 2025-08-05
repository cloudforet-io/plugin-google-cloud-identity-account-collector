from pathlib import Path

import yaml


def load_pagination_config():
    config_path = Path(__file__).parent / "api_pagination.yaml"
    if config_path.exists():
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    return {"api_pagination": {"default": {"page_size": 200}}}


PAGINATION_CONFIG = load_pagination_config()
