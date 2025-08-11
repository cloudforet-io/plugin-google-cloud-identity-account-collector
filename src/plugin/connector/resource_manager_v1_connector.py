import logging

from plugin.connector.base_connector import GoogleCloudConnector

__all__ = ["ResourceManagerV1Connector"]

_LOGGER = logging.getLogger(__name__)


class ResourceManagerV1Connector(GoogleCloudConnector):
    google_client_service = "cloudresourcemanager"
    version = "v1"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.secret_data = kwargs.get("secret_data", {})

    def list_projects(self, filter=None):
        return self.list_with_pagination(
            self.client.projects().list, method_name="list_projects", filter=filter
        )
