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

    def get_project(self):
        name = f"projects/{self.secret_data['project_id']}"
        return self.client.projects().get(name=name).execute()

    def list_projects(self):
        result = self.client.projects().list().execute()
        return result.get("projects", [])
