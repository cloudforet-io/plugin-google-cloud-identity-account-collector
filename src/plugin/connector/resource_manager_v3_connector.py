import logging

from plugin.connector.base_connector import GoogleCloudConnector

__all__ = ["ResourceManagerV3Connector"]

_LOGGER = logging.getLogger(__name__)


class ResourceManagerV3Connector(GoogleCloudConnector):
    google_client_service = "cloudresourcemanager"
    version = "v3"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.secret_data = kwargs.get("secret_data", {})

    def get_project(self):
        name = f"projects/{self.secret_data['project_id']}"
        return self.client.projects().get(name=name).execute()

    def list_projects_by_organization_id(self, organization_id):
        result = self.client.projects().list(parent=organization_id).execute()
        return result.get("projects", [])

    def get_organization(self, organization_id):
        return self.client.organizations().get(name=organization_id).execute()

    def list_folders_by_organization_id(self, organization_id):
        return self.client.folders().list(parent=organization_id).execute()
