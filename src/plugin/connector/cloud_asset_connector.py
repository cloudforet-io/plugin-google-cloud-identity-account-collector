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

    def list_iam_polices_in_project(self, project_id):
        total_assets = []
        query = {
            "parent": f"projects/{project_id}",
            "contentType": "IAM_POLICY",
            "assetTypes": "cloudresourcemanager.googleapis.com.Project",
            "pageSize": 1000,
        }
        request = self.client.assets().list(**query)

        while request is not None:
            response = request.execute()
            for asset in response.get("assets", {}):
                total_assets.append(asset)
            request = self.client.assets().list_next(
                previous_request=request, previous_response=response
            )
        return total_assets
