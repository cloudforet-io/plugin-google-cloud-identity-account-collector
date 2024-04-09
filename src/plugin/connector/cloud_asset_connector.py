import logging

from plugin.connector.base_connector import GoogleCloudConnector

__all__ = ["CloudAssetConnector"]

_LOGGER = logging.getLogger(__name__)


class CloudAssetConnector(GoogleCloudConnector):
    google_client_service = "cloudasset"
    version = "v1"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.secret_data = kwargs.get("secret_data", {})

    def list_service_account(self, **query):
        query.update(
            {
                "parent": f"projects/{self.project_id}",
                "pageSize": 1000,
            }
        )
        return self.client.assets().list(**query)
