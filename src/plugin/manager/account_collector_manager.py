import logging
from spaceone.core.manager import BaseManager
from plugin.connector.resource_manager_v1_connector import ResourceManagerV1Connector
from plugin.connector.resource_manager_v3_connector import ResourceManagerV3Connector

_LOGGER = logging.getLogger("spaceone")


class AccountCollectorManager(BaseManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = kwargs["options"]
        self.secret_data = kwargs["secret_data"]
        self.resource_manager_v1_connector = ResourceManagerV1Connector(
            secret_data=self.secret_data
        )
        self.resource_manager_v3_connector = ResourceManagerV3Connector(
            secret_data=self.secret_data
        )

    def sync(self) -> list:
        """sync Google Cloud resources
            :Returns:
                results [
                {
                    name: 'str',
                    data: 'dict',
                    secret_schema_id: 'str',
                    secret_data: 'dict',
                    tags: 'dict',
                    location: 'list'
                }
        ]
        """
        results = []
        exclude_projects = self.options.get("exclude_projects", [])

        projects_info = self.resource_manager_v1_connector.list_projects()
        # organization_info = self._get_organization_info(projects_info)
        #
        # if not organization_info:
        #     raise Exception(
        #         "[sync] The Organization belonging to this ServiceAccount cannot be found."
        #     )

        organization_info = {
            "displayName": "Google Cloud Test",
            "name": "organizations/597078905893",
        }
        organization_name = organization_info["displayName"]
        organization_id = organization_info["name"]

        for project_info in projects_info:
            project_id = project_info["projectId"]
            project_name = project_info["name"]
            project_state = project_info["lifecycleState"]
            project_tags = project_info.get("labels", {})

            if project_id not in exclude_projects and project_state == "ACTIVE":
                result = {
                    "name": project_name,
                    "data": {
                        "project_id": project_id,
                    },
                    "secret_schema_id": "google-secret-project-id",
                    "secret_data": {
                        "project_id": project_id,
                    },
                    "resource_id": project_id,
                    "tags": project_tags,
                    "location": [
                        {"name": organization_name, "resource_id": organization_id}
                    ],
                }

                results.append(result)

        return results

    def _get_organization_info(self, projects_info):
        organization_info = {}
        organization_parent = None
        for project_info in projects_info:
            if organization_info:
                break

            parent = project_info.get("parent")
            if (
                parent
                and parent.get("type") == "organization"
                and not organization_parent
            ):
                organization_parent = f"organizations/{parent['id']}"
                organization_info = self.resource_manager_v3_connector.get_organization(
                    organization_parent
                )
        return organization_info
