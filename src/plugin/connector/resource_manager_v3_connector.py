import logging
import itertools

from plugin.connector.base_connector import GoogleCloudConnector

__all__ = ["ResourceManagerV3Connector"]

_LOGGER = logging.getLogger(__name__)


class ResourceManagerV3Connector(GoogleCloudConnector):
    google_client_service = "cloudresourcemanager"
    version = "v3"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.secret_data = kwargs.get("secret_data", {})

    def list_projects(self, parent, filter=None):
        projects = self.list_with_pagination(
            self.client.projects().list, method_name="list_projects", parent=parent
        )

        if filter and "state:ACTIVE" in filter:
            projects = [p for p in projects if p.get("state") == "ACTIVE"]

        return projects

    def get_organization(self, organization_id):
        return self.client.organizations().get(name=organization_id).execute()

    def list_folders(self, parent):
        return self.list_with_pagination(
            self.client.folders().list, method_name="list_folders", parent=parent
        )

    def list_role_bindings(self, resource):
        result = self.client.projects().getIamPolicy(resource=resource).execute()
        bindings = result.get("bindings", [])
        return list(itertools.chain(*[binding["members"] for binding in bindings]))

    def search_folders(self):
        return self.list_with_pagination(
            self.client.folders().search, method_name="search_folders"
        )
