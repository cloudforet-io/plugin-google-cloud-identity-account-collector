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

    # [DEPRECATED] DO NOT USE THISE METHOD. USE list_all_projects() INSTEAD. WHERE IS PAGE TOKEN???
    # https://docs.cloud.google.com/resource-manager/reference/rest/v1/projects/list
    # If the result set is too large to fit in a single response, this token is returned.
    # It encodes the position of the current result cursor.
    # Feeding this value into a new list request with the pageToken parameter gives the next page of the results.
    def list_projects(self):
        result = self.client.projects().list().execute()
        return result.get("projects", [])

    # use v3 than v1 method to ignore require parent parameter.
    def list_all_projects(self):
        pagetoken = None
        all_projects = []
        while True:
            results = self.client.projects().list(pageToken=pagetoken).execute()
            all_projects.extend(results.get("projects", []))
            pagetoken = results.get("nextPageToken")
            if not pagetoken:
                break
        return all_projects
