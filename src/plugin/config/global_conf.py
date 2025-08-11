from pathlib import Path

import yaml


def load_pagination_config():
    # 프로젝트 루트의 api_pagination.yaml 파일을 찾기
    config_path = Path(__file__).parent.parent.parent.parent / "api_pagination.yaml"

    if config_path.exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
            return config
    else:
        return {"api_pagination": {"default": {"page_size": 200}}}


PAGINATION_CONFIG = load_pagination_config()
