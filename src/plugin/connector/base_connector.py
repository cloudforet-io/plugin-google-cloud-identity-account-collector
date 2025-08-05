import logging

import google.oauth2.service_account
import googleapiclient
import googleapiclient.discovery
from spaceone.core.connector import BaseConnector

from plugin.config.global_conf import PAGINATION_CONFIG

_LOGGER = logging.getLogger(__name__)


class GoogleCloudConnector(BaseConnector):
    google_client_service = None
    version = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        secret_data = kwargs.get("secret_data")
        self.project_id = secret_data.get("project_id")
        self.credentials = (
            google.oauth2.service_account.Credentials.from_service_account_info(
                secret_data
            )
        )
        self.client = googleapiclient.discovery.build(
            self.google_client_service,
            self.version,
            credentials=self.credentials,
        )

    def generate_query(self, **query):
        query.update(
            {
                "project": self.project_id,
            }
        )
        return query

    def get_page_size(self, method_name=None):
        config = PAGINATION_CONFIG.get("api_pagination", {})
        connector_name = f"{self.google_client_service}_{self.version}"

        if connector_name in config:
            connector_config = config[connector_name]

            if method_name and "methods" in connector_config:
                method_config = connector_config["methods"].get(method_name)
                if method_config:
                    return method_config.get(
                        "page_size", connector_config.get("page_size", 200)
                    )

            return connector_config.get("page_size", 200)

        return config.get("default", {}).get("page_size", 200)

    def list_with_pagination(self, method, method_name=None, **kwargs):
        page_size = self.get_page_size(method_name)
        all_results = []
        page_token = None

        while True:
            params = kwargs.copy()
            params["pageSize"] = page_size

            if page_token:
                params["pageToken"] = page_token

            try:
                result = method(**params).execute()
                items = result.get(
                    "projects", result.get("folders", result.get("organizations", []))
                )
                all_results.extend(items)

                page_token = result.get("nextPageToken")
                if not page_token:
                    break

            except Exception as e:
                _LOGGER.error(f"Error during pagination: {e}")
                break

        return all_results
