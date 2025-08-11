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
        try:
            config = PAGINATION_CONFIG.get("api_pagination", {})
            connector_name = f"{self.google_client_service}_{self.version}"
            default_page_size = config.get("default", {}).get("page_size", 200)

            _LOGGER.debug(
                f"[PAGINATION] get_page_size - connector_name: {connector_name}, method_name: {method_name}"
            )

            if connector_name in config:
                connector_config = config[connector_name]
                connector_page_size = connector_config.get(
                    "page_size", default_page_size
                )

                if method_name and "methods" in connector_config:
                    method_config = connector_config["methods"].get(method_name)
                    if method_config:
                        page_size = method_config.get("page_size", connector_page_size)
                        _LOGGER.debug(
                            f"[PAGINATION] Using method-specific page_size: {page_size}"
                        )
                        return page_size

                _LOGGER.debug(
                    f"[PAGINATION] Using connector page_size: {connector_page_size}"
                )
                return connector_page_size

            _LOGGER.debug(f"[PAGINATION] Using default page_size: {default_page_size}")
            return default_page_size
        except Exception as e:
            _LOGGER.error(f"[PAGINATION] Error in get_page_size: {e}")
            return 200

    def list_with_pagination(self, method, method_name=None, **kwargs):
        page_size = self.get_page_size(method_name)
        all_results = []
        page_token = None
        page_count = 0

        _LOGGER.debug(f"[PAGINATION] {method_name}: page_size={page_size}")

        while True:
            page_count += 1
            params = kwargs.copy()
            params["pageSize"] = page_size

            if page_token:
                params["pageToken"] = page_token

            try:
                result = method(**params).execute()
                items = result.get(
                    "projects", result.get("folders", result.get("organizations", []))
                )

                _LOGGER.debug(
                    f"[PAGINATION] {method_name}: page {page_count} -> {len(items)} items"
                )

                all_results.extend(items)
                page_token = result.get("nextPageToken")

                if not page_token:
                    _LOGGER.debug(
                        f"[PAGINATION] {method_name}: No more pages (no nextPageToken)"
                    )
                    break

            except Exception as e:
                _LOGGER.error(f"[PAGINATION] Error in {method_name}: {e}")
                break

        _LOGGER.debug(
            f"[PAGINATION] === END list_with_pagination === total: {len(all_results)} items"
        )
        return all_results
