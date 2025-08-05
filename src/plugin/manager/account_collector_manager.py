import fnmatch
import logging
from collections import deque

from spaceone.core.manager import BaseManager

from plugin.connector.resource_manager_v1_connector import ResourceManagerV1Connector
from plugin.connector.resource_manager_v3_connector import ResourceManagerV3Connector

_LOGGER = logging.getLogger("spaceone")


class AccountCollectorManager(BaseManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.options = kwargs["options"]
        self.trusting_organization = self.options.get("trusting_organization", True)
        self.exclude_projects = self.options.get("exclude_projects", [])
        self.exclude_folders = [
            str(int(folder_id)) for folder_id in self.options.get("exclude_folders", [])
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
        self.processed_project_ids = set()

    def sync(self) -> list:
        all_projects_info = self.resource_manager_v1_connector.list_projects(
            filter="state:ACTIVE"
        )

        organizations_info = self._get_organizations_info(all_projects_info)

        dq = deque()
        if organizations_info:
            visited = set()
            for org_info in organizations_info:
                parent = org_info["name"]
                dq.append((parent, []))

            while dq:
                current_parent, current_locations = dq.popleft()
                if current_parent in visited:
                    continue
                visited.add(current_parent)

                self._create_project_response(current_parent, current_locations)

                folders_info = self.resource_manager_v3_connector.list_folders(
                    current_parent
                )
                for folder_info in folders_info:
                    folder_id = folder_info["name"].split("/")[-1]
                    if folder_id in self.exclude_folders:
                        continue
                    folder_name = folder_info["displayName"]
                    folder_parent = folder_info["name"]
                    next_locations = current_locations + [
                        {"name": folder_name, "resource_id": folder_parent}
                    ]
                    dq.append((folder_parent, next_locations))

        _LOGGER.info("Searching for projects without an organization.")
        no_org_projects = [p for p in all_projects_info if not p.get("parent")]
        if no_org_projects:
            _LOGGER.debug(
                f"Found {len(no_org_projects)} projects without an organization."
            )
            self._process_project_list(no_org_projects, [])

        return self.results

    def _get_organizations_info(self, projects_info: list) -> list:
        organizations = {}

        for project_info in projects_info:
            parent = project_info.get("parent")
            if parent and parent.get("type") == "organization":
                org_name = f"organizations/{parent['id']}"
                if org_name not in organizations:
                    organization_info = (
                        self.resource_manager_v3_connector.get_organization(org_name)
                    )
                    if organization_info:
                        organizations[org_name] = organization_info

        for folder_info in self.resource_manager_v3_connector.search_folders():
            parent = folder_info.get("parent")
            if parent and parent.startswith("organizations"):
                if parent not in organizations:
                    organization_info = (
                        self.resource_manager_v3_connector.get_organization(parent)
                    )
                    if organization_info:
                        organizations[parent] = organization_info

        if organizations:
            org_names = [org["name"] for org in organizations.values()]
            _LOGGER.debug(f"[sync] Organizations to sync: {org_names}")
        else:
            _LOGGER.debug(
                "[sync] No organizations found. Proceeding to find projects without an organization."
            )

        return list(organizations.values())

    def _create_project_response(self, parent, locations):
        try:
            projects_info = self.resource_manager_v3_connector.list_projects(
                parent, filter="state:ACTIVE"
            )
            self._process_project_list(projects_info, locations)
        except Exception as e:
            _LOGGER.error(f"[sync] Failed to list projects under {parent} => {e}")
            return

    def _process_project_list(self, projects_info: list, locations: list):
        for project_info in projects_info or []:
            project_id = project_info["projectId"]

            if project_id in self.processed_project_ids:
                continue

            project_state = project_info["state"]
            if not self._should_include_project(project_id, project_state):
                continue

            result_to_add = None
            if self.trusting_organization:
                _LOGGER.debug(
                    f"[sync] ServiceAccount is Trusted with Organization (Project ID: {project_id})"
                )
                result_to_add = self._make_result(project_info, locations)
            elif self._is_trusting_project(project_id):
                result_to_add = self._make_result(project_info, locations)
            else:
                result_to_add = self._make_result(
                    project_info, locations, is_secret_data=False
                )

            if result_to_add:
                self.results.append(result_to_add)
                self.processed_project_ids.add(project_id)

    def _should_include_project(self, project_id, state=None):
        if state and state != "ACTIVE":
            return False
        return self._check_exclude_project(project_id)

    def _is_trusting_project(self, project_id) -> bool:
        try:
            role_bindings = self.resource_manager_v3_connector.list_role_bindings(
                resource=f"projects/{project_id}"
            )
            _LOGGER.debug(
                f"[sync] {self.trusted_service_account} / {project_id} role_bindings: {role_bindings}"
            )
            return f"serviceAccount:{self.trusted_service_account}" in role_bindings
        except Exception as e:
            _LOGGER.error(f"[sync] Failed to get role_bindings for {project_id} => {e}")
            return False

    def _check_exclude_project(self, project_id):
        return not any(
            fnmatch.fnmatch(project_id, exclude_id)
            for exclude_id in self.exclude_projects
        )

    @staticmethod
    def _make_result(project_info, locations, is_secret_data=True):
        project_id = project_info["projectId"]
        project_name = project_info["displayName"]
        project_tags = project_info.get("labels", {})

        result = {
            "name": project_name,
            "data": {"project_id": project_id},
            "secret_schema_id": "google-secret-project-id",
            "resource_id": project_id,
            "tags": project_tags,
            "location": locations,
        }

        if is_secret_data:
            result["secret_data"] = {"project_id": project_id}
        return result
