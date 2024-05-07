from spaceone.identity.plugin.account_collector.lib.server import (
    AccountCollectorPluginServer,
)
from plugin.manager.account_collector_manager import AccountCollectorManager

app = AccountCollectorPluginServer()


@app.route("AccountCollector.init")
def account_collector_init(params: dict) -> dict:
    """init plugin by options

    Args:
        params (CollectorInitRequest): {
            'options': 'dict',    # Required
            'domain_id': 'str'
        }

    Returns:
        PluginResponse: {
            'metadata': 'dict'
        }
    """
    options = params.get("options", {}) or {}

    metadata = {
        "additional_options_schema": {
            "type": "object",
            "properties": {
                "trusting_organization": {
                    "title": "Trusting Organization",
                    "type": "boolean",
                    "default": True,
                },
                "exclude_projects": {
                    "title": "Exclude Projects",
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Supports Unix filename pattern matching. ex ['sys-*']",
                },
                "exclude_folders": {
                    "title": "Exclude Folders",
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Enter the Folder ID to exclude.",
                },
            },
        }
    }

    additional_options_schema = metadata["additional_options_schema"]

    if trusting_organization := options.get("trusting_organization"):
        additional_options_schema["properties"]["trusting_organization"][
            "default"
        ] = trusting_organization

    if exclude_projects := options.get("exclude_projects"):
        additional_options_schema["properties"]["exclude_projects"][
            "default"
        ] = exclude_projects

    if exclude_folders := options.get("exclude_folders"):
        additional_options_schema["properties"]["exclude_folders"][
            "default"
        ] = exclude_folders

    metadata["additional_options_schema"] = additional_options_schema
    return {"metadata": metadata}


@app.route("AccountCollector.sync")
def account_collector_sync(params: dict) -> dict:
    """AccountCollector sync

    Args:
        params (AccountCollectorInit): {
            'options': 'dict',          # Required
            'schema_id': 'str',
            'secret_data': 'dict',      # Required
            'domain_id': 'str'          # Required
        }

    Returns:
        AccountsResponse:
        {
            'results': [
                {
                    name: 'str',
                    data: 'dict',
                    secret_schema_id: 'str',
                    secret_data: 'dict',
                    tags: 'dict',
                    location: 'list'
                }
            ]
        }
    """
    return {"results": AccountCollectorManager(**params).sync()}
