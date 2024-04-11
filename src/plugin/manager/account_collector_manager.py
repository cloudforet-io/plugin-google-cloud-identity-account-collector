import copy
import fnmatch
import logging
from collections import deque
from time import sleep

from spaceone.core.manager import BaseManager
from plugin.connector.resource_manager_v1_connector import ResourceManagerV1Connector
from plugin.connector.resource_manager_v3_connector import ResourceManagerV3Connector

_LOGGER = logging.getLogger("spaceone")


class AccountCollectorManager(BaseManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = kwargs["options"]
        self.trusting_organization = self.options.get("trusting_organization", False)
        self.exclude_projects = self.options.get("exclude_projects", [])
        self.exclude_folders = self.options.get("exclude_folders", [])
        self.exclude_folders = [
            str(int(folder_id)) for folder_id in self.exclude_folders
        ]

        self.secret_data = kwargs["secret_data"]
        self.trusted_service_account = self.secret_data["client_email"]

        self.resource_manager_v1_connector = ResourceManagerV1Connector(
            secret_data=self.secret_data
        )
        self.resource_manager_v3_connector = ResourceManagerV3Connector(
            secret_data=self.secret_data
        )
        self.results = []

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
        projects_info = self.resource_manager_v1_connector.list_projects()
        organization_info = self._get_organization_info(projects_info)

        parent = organization_info["name"]

        dq = deque()
        dq.append([parent, []])
        while dq:
            for idx in range(len(dq)):
                parent, current_locations = dq.popleft()
                self._create_project_response(parent, current_locations)

                folders_info = self.resource_manager_v3_connector.list_folders(parent)
                for folder_info in folders_info:
                    folder_parent = folder_info["name"]
                    prefix, folder_id = folder_info["name"].split("/")
                    folder_name = folder_info["displayName"]
                    if folder_id not in self.exclude_folders:
                        parent = folder_parent
                        next_locations = copy.deepcopy(current_locations)
                        next_locations.append(
                            {"name": folder_name, "resource_id": folder_parent}
                        )
                        dq.append([parent, next_locations])
        return self.results

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

        if not organization_info:
            for folder_info in self.resource_manager_v3_connector.search_folders():
                parent = folder_info.get("parent")
                if parent.startswith("organizations"):
                    organization_parent = parent
                    organization_info = (
                        self.resource_manager_v3_connector.get_organization(
                            organization_parent
                        )
                    )

        if not organization_info:
            raise Exception(
                "[sync] The Organization belonging to this ServiceAccount cannot be found."
            )

        _LOGGER.debug(f"[sync] Organization information to sync: {organization_info}")

        return organization_info

    @staticmethod
    def _make_result(project_info, locations, is_secret_data=True):
        project_id = project_info["projectId"]
        project_name = project_info["displayName"]
        project_tags = project_info.get("labels", {})
        result = {
            "name": project_name,
            "data": {
                "project_id": project_id,
            },
            "secret_schema_id": "google-secret-project-id",
            "resource_id": project_id,
            "tags": project_tags,
            "location": locations,
        }

        if is_secret_data:
            result["secret_data"] = {
                "project_id": project_id,
            }

        return result

    def _create_project_response(self, parent, locations):
        projects_info = self.resource_manager_v3_connector.list_projects(parent)

        if projects_info:
            for project_info in projects_info:
                project_id = project_info["projectId"]
                project_state = project_info["state"]

                if (
                    self._check_exclude_project(project_id)
                    and project_state == "ACTIVE"
                ):
                    if self.trusting_organization:
                        _LOGGER.debug(
                            f"[sync] ServiceAccount is Trusted with Organization (ServiceAccount: {self.trusted_service_account}, Project ID: {project_id})"
                        )
                        self.results.append(self._make_result(project_info, locations))
                    elif self._is_trusting_project(project_id):
                        self.results.append(self._make_result(project_info, locations))
                    else:
                        self.results.append(
                            self._make_result(
                                project_info, locations, is_secret_data=False
                            )
                        )

    def _is_trusting_project(self, project_id):
        try:
            role_bindings = self.resource_manager_v3_connector.list_role_bindings(
                resource=f"projects/{project_id}"
            )
            _LOGGER.debug(
                f"[sync]{self.trusted_service_account} / {project_id} of role_bindings: {role_bindings}"
            )
        except Exception as e:
            _LOGGER.error(f"[sync] failed to get role_bindings => {e}")
            return False

        if f"serviceAccount:{self.trusted_service_account}" in role_bindings:
            return True
        else:
            return False

    def _check_exclude_project(self, project_id):
        for exclude_project_id in self.exclude_projects:
            if fnmatch.fnmatch(project_id, exclude_project_id):
                return False
        return True
