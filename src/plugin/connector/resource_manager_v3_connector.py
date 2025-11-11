import itertools
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

    def list_projects(self, parent):
        result = self.client.projects().list(parent=parent).execute()
        return result.get("projects", [])

    def get_organization(self, organization_id):
        return self.client.organizations().get(name=organization_id).execute()

    def list_folders(self, parent):
        results = self.client.folders().list(parent=parent).execute()
        return results.get("folders", [])

    def list_role_bindings(self, resource):
        result = self.client.projects().getIamPolicy(resource=resource).execute()
        bindings = result.get("bindings", [])
        return list(itertools.chain(*[binding["members"] for binding in bindings]))

    def search_folders(self):
        results = self.client.folders().search().execute()
        return results.get("folders", [])

    def search_all_folders(self):
        """
        https://docs.cloud.google.com/resource-manager/reference/rest/v3/folders/search
        Search Method, but return all folders with none query. more efficient than list recursive.
        """
        pagetoken = None
        all_folders = []
        while True:
            results = self.client.folders().search(pageToken=pagetoken).execute()
            all_folders.extend(results.get("folders", []))
            pagetoken = results.get("nextPageToken")
            if not pagetoken:
                break
        return all_folders
