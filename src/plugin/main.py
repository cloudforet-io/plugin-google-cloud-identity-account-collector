import logging
import os

from spaceone.identity.plugin.account_collector.lib.server import (
    AccountCollectorPluginServer,
)

from plugin.manager.account_collector_manager import AccountCollectorManager

app = AccountCollectorPluginServer()

_LOGGER = logging.getLogger("spaceone")


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
                "start_depth": {
                    "title": "Start Depth",
                    "type": "integer",
                    "default": 0,
                    "minimum": 0,
                    "description": "Depth level to start collection from. 0=Organization, 1=First level folders, 2=Second level folders, etc.",
                },
                "include_location_from_depth": {
                    "title": "Include Location From Depth",
                    "type": "integer",
                    "default": 0,
                    "minimum": 0,
                    "description": "Depth level to start including folder location in project path. Must be less than or equal to start_depth. If not set, uses start_depth value.",
                },
            },
        }
    }

    additional_options_schema = metadata["additional_options_schema"]

    if trusting_organization := options.get("trusting_organization"):
        additional_options_schema["properties"]["trusting_organization"]["default"] = (
            trusting_organization
        )

    if exclude_projects := options.get("exclude_projects"):
        additional_options_schema["properties"]["exclude_projects"]["default"] = (
            exclude_projects
        )

    if exclude_folders := options.get("exclude_folders"):
        additional_options_schema["properties"]["exclude_folders"]["default"] = (
            exclude_folders
        )

    if start_depth := options.get("start_depth"):
        additional_options_schema["properties"]["start_depth"]["default"] = start_depth

    if include_location_from_depth := options.get("include_location_from_depth"):
        additional_options_schema["properties"]["include_location_from_depth"][
            "default"
        ] = include_location_from_depth

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
    proxy_env = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if proxy_env:
        _LOGGER.debug(
            f"** Using proxy in environment variable HTTPS_PROXY/https_proxy: {proxy_env}"
        )  # src/plugin/connector/base_connector.py _create_http_client

    return {"results": AccountCollectorManager(**params).sync()}
