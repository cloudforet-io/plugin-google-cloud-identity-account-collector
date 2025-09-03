import fnmatch
import logging
from collections import deque
from functools import lru_cache

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
        self.exclude_folders = self.options.get("exclude_folders", [])
        self.exclude_folders = [
            str(int(folder_id)) for folder_id in self.exclude_folders
        ]
        self.start_depth = self.options.get("start_depth", 0)

        # include_location_from_depth 옵션 처리
        include_location_from_depth = self.options.get("include_location_from_depth")
        if include_location_from_depth is None:
            # include_location_from_depth가 없으면 start_depth 사용
            self.include_location_from_depth = self.start_depth
        else:
            self.include_location_from_depth = include_location_from_depth

        # include_location_from_depth는 start_depth보다 클 수 없음
        if self.include_location_from_depth > self.start_depth:
            raise ValueError(
                f"include_location_from_depth ({self.include_location_from_depth}) "
                f"cannot be greater than start_depth ({self.start_depth})"
            )
        self.secret_data = kwargs["secret_data"]
        self.trusted_service_account = self.secret_data["client_email"]

        self.resource_manager_v1_connector = ResourceManagerV1Connector(
            secret_data=self.secret_data
        )
        self.resource_manager_v3_connector = ResourceManagerV3Connector(
            secret_data=self.secret_data
        )
        self.results = []

        # 방문 기록을 위한 set
        self.visited_folders = set()

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
        _LOGGER.info(
            f"[sync] Starting sync process with start_depth: {self.start_depth}, "
            f"include_location_from_depth: {self.include_location_from_depth}"
        )

        projects_info = self.resource_manager_v1_connector.list_projects()
        organization_info = self._get_organization_info(projects_info)

        parent = organization_info["name"]
        _LOGGER.info(
            f"[sync] Organization found: {organization_info.get('displayName', 'Unknown')} ({parent})"
        )

        queue = deque()
        queue.append((parent, [], 0))  # (parent, locations, current_depth)

        # 방문 기록 초기화
        self.visited_folders.clear()

        while queue:
            level_size = len(queue)

            for _ in range(level_size):
                parent, current_locations, current_depth = queue.popleft()

                _LOGGER.debug(f"[sync] Processing at depth {current_depth}: {parent}")
                _LOGGER.debug(f"[sync] Current locations: {current_locations}")

                # start_depth에 도달했을 때만 프로젝트 수집 시작
                if current_depth >= self.start_depth:
                    _LOGGER.debug(
                        f"[sync] Collecting projects at depth {current_depth} (start_depth: {self.start_depth})"
                    )
                    self._create_project_response(parent, current_locations)
                else:
                    _LOGGER.debug(
                        f"[sync] Skipping project collection at depth {current_depth} (start_depth: {self.start_depth})"
                    )

                folders_info = self._get_folders_cached(parent)
                _LOGGER.debug(
                    f"[sync] Found {len(folders_info)} folders at depth {current_depth}"
                )

                for folder_info in folders_info:
                    folder_parent = folder_info["name"]
                    prefix, folder_id = folder_info["name"].split("/")
                    folder_name = folder_info["displayName"]

                    _LOGGER.debug(
                        f"[sync] Processing folder: {folder_name} (ID: {folder_id}) at depth {current_depth}"
                    )

                    # 방문 기록 확인 (무한 루프 방지)
                    if folder_parent in self.visited_folders:
                        _LOGGER.warning(
                            f"[sync] Circular reference detected, skipping folder: {folder_name} ({folder_parent})"
                        )
                        continue

                    if folder_id not in self.exclude_folders:
                        # 방문 기록 추가
                        self.visited_folders.add(folder_parent)

                        next_depth = current_depth + 1

                        # include_location_from_depth에 도달한 경우에만 locations에 폴더 정보 추가
                        if current_depth >= self.include_location_from_depth:
                            next_locations = current_locations + [
                                {"name": folder_name, "resource_id": folder_parent}
                            ]
                            _LOGGER.debug(
                                f"[sync] Adding folder to queue with location tracking: {folder_name} at depth {next_depth} (include_location_from_depth: {self.include_location_from_depth})"
                            )
                        else:
                            # include_location_from_depth에 도달하지 않은 경우 locations는 그대로 유지
                            next_locations = current_locations
                            _LOGGER.debug(
                                f"[sync] Adding folder to queue without location tracking: {folder_name} at depth {next_depth} (include_location_from_depth: {self.include_location_from_depth})"
                            )

                        queue.append((folder_parent, next_locations, next_depth))
                    else:
                        _LOGGER.debug(
                            f"[sync] Excluding folder: {folder_name} (ID: {folder_id})"
                        )

        _LOGGER.info(
            f"[sync] Sync completed. Total projects collected: {len(self.results)}"
        )
        return self.results

    @lru_cache(maxsize=100)
    def _get_folders_cached(self, parent):
        """폴더 목록을 캐싱하여 API 호출 최적화"""
        return self.resource_manager_v3_connector.list_folders(parent)

    @lru_cache(maxsize=50)
    def _get_projects_cached(self, parent):
        """프로젝트 목록을 캐싱하여 API 호출 최적화"""
        return self.resource_manager_v3_connector.list_projects(parent)

    def _get_organization_info(self, projects_info):
        _LOGGER.debug(
            f"[get_organization_info] Searching for organization from {len(projects_info)} projects"
        )

        organization_info = {}
        organization_parent = None
        checked_projects = 0
        checked_folders = 0

        # 프로젝트에서 조직 정보 찾기
        for project_info in projects_info:
            if organization_info:
                break

            checked_projects += 1
            parent = project_info.get("parent")
            project_id = project_info.get("projectId", "Unknown")

            _LOGGER.debug(
                f"[get_organization_info] Checking project {project_id} parent: {parent}"
            )

            if (
                parent
                and parent.get("type") == "organization"
                and not organization_parent
            ):
                organization_parent = f"organizations/{parent['id']}"
                _LOGGER.debug(
                    f"[get_organization_info] Found organization from project: {organization_parent}"
                )
                try:
                    organization_info = (
                        self.resource_manager_v3_connector.get_organization(
                            organization_parent
                        )
                    )
                except Exception as e:
                    error_msg = str(e).lower()
                    if (
                        "permission" in error_msg
                        or "forbidden" in error_msg
                        or "403" in error_msg
                    ):
                        _LOGGER.error(
                            f"[get_organization_info] Permission denied for organization {organization_parent} from project {project_id}: {e}"
                        )
                        raise Exception(
                            f"[sync] Permission denied. Cannot access organization {organization_parent}. "
                            f"Service account needs 'resourcemanager.organizations.get' permission. Error: {e}"
                        )
                    else:
                        _LOGGER.warning(
                            f"[get_organization_info] Failed to get organization {organization_parent} from project {project_id}: {e}"
                        )
                        organization_info = {}
                        organization_parent = None

        # 프로젝트에서 찾지 못한 경우 폴더에서 찾기
        if not organization_info:
            _LOGGER.debug(
                "[get_organization_info] Organization not found in projects, searching in folders"
            )
            try:
                folders_info = self.resource_manager_v3_connector.search_folders()
                _LOGGER.debug(
                    f"[get_organization_info] Found {len(folders_info)} folders to check"
                )

                for folder_info in folders_info:
                    if organization_info:
                        break

                    checked_folders += 1
                    parent = folder_info.get("parent")
                    folder_name = folder_info.get("displayName", "Unknown")

                    _LOGGER.debug(
                        f"[get_organization_info] Checking folder {folder_name} parent: {parent}"
                    )

                    if parent and parent.startswith("organizations"):
                        organization_parent = parent
                        _LOGGER.debug(
                            f"[get_organization_info] Found organization from folder: {organization_parent}"
                        )
                        try:
                            organization_info = (
                                self.resource_manager_v3_connector.get_organization(
                                    organization_parent
                                )
                            )
                        except Exception as e:
                            error_msg = str(e).lower()
                            if (
                                "permission" in error_msg
                                or "forbidden" in error_msg
                                or "403" in error_msg
                            ):
                                _LOGGER.error(
                                    f"[get_organization_info] Permission denied for organization {organization_parent} from folder {folder_name}: {e}"
                                )
                                raise Exception(
                                    f"[sync] Permission denied. Cannot access organization {organization_parent}. "
                                    f"Service account needs 'resourcemanager.organizations.get' permission."
                                )
                            else:
                                _LOGGER.warning(
                                    f"[get_organization_info] Failed to get organization {organization_parent} from folder {folder_name}: {e}"
                                )
                                organization_info = {}
                                organization_parent = None

            except Exception as e:
                error_msg = str(e).lower()
                if (
                    "permission" in error_msg
                    or "forbidden" in error_msg
                    or "403" in error_msg
                ):
                    _LOGGER.error(
                        f"[get_organization_info] Permission denied for folder search: {e}"
                    )
                    raise Exception(
                        "[sync] Permission denied. Cannot search folders. "
                        "Service account needs 'resourcemanager.folders.search' permission."
                    )
                else:
                    _LOGGER.error(
                        f"[get_organization_info] Failed to search folders: {e}"
                    )

        if not organization_info:
            error_details = []
            if checked_projects > 0:
                error_details.append(f"checked {checked_projects} projects")
            if checked_folders > 0:
                error_details.append(f"checked {checked_folders} folders")

            error_message = "[sync] No organization found for service account. "
            if error_details:
                error_message += f"Details: {' and '.join(error_details)}"
            else:
                error_message += "No projects or folders were accessible."

            _LOGGER.error(f"[get_organization_info] {error_message}")
            raise Exception(error_message)

        _LOGGER.info(
            f"[get_organization_info] Organization found: {organization_info.get('displayName', 'Unknown')} ({organization_info.get('name', 'Unknown')}) after checking {checked_projects} projects and {checked_folders} folders"
        )

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
        projects_info = self._get_projects_cached(parent)

        _LOGGER.debug(
            f"[create_project_response] Checking projects for parent: {parent}"
        )
        _LOGGER.debug(
            f"[create_project_response] Found {len(projects_info) if projects_info else 0} projects"
        )

        if projects_info:
            for project_info in projects_info:
                project_id = project_info["projectId"]
                project_name = project_info.get("displayName", "Unknown")
                project_state = project_info["state"]

                _LOGGER.debug(
                    f"[create_project_response] Processing project: {project_name} (ID: {project_id}, State: {project_state})"
                )

                if (
                    self._check_exclude_project(project_id)
                    and project_state == "ACTIVE"
                ):
                    _LOGGER.debug(
                        f"[create_project_response] Project {project_name} passed filters, checking permissions"
                    )

                    if self.trusting_organization:
                        _LOGGER.debug(
                            f"[create_project_response] ServiceAccount is Trusted with Organization (ServiceAccount: {self.trusted_service_account}, Project ID: {project_id})"
                        )
                        self.results.append(self._make_result(project_info, locations))
                        _LOGGER.debug(
                            f"[create_project_response] Added project {project_name} with secret_data"
                        )
                    elif self._is_trusting_project(project_id):
                        self.results.append(self._make_result(project_info, locations))
                        _LOGGER.debug(
                            f"[create_project_response] Added project {project_name} with secret_data (project-level trust)"
                        )
                    else:
                        self.results.append(
                            self._make_result(
                                project_info, locations, is_secret_data=False
                            )
                        )
                        _LOGGER.debug(
                            f"[create_project_response] Added project {project_name} without secret_data (no permissions)"
                        )
                else:
                    if not self._check_exclude_project(project_id):
                        _LOGGER.debug(
                            f"[create_project_response] Project {project_name} excluded by pattern"
                        )
                    if project_state != "ACTIVE":
                        _LOGGER.debug(
                            f"[create_project_response] Project {project_name} excluded by state: {project_state}"
                        )
        else:
            _LOGGER.debug(
                f"[create_project_response] No projects found for parent: {parent}"
            )

    def _is_trusting_project(self, project_id):
        try:
            _LOGGER.debug(
                f"[is_trusting_project] Checking IAM permissions for project: {project_id}"
            )
            role_bindings = self.resource_manager_v3_connector.list_role_bindings(
                resource=f"projects/{project_id}"
            )
            _LOGGER.debug(
                f"[is_trusting_project] ServiceAccount: {self.trusted_service_account} / Project: {project_id} / Role bindings: {role_bindings}"
            )
        except Exception as e:
            _LOGGER.error(
                f"[is_trusting_project] Failed to get role_bindings for project {project_id} => {e}"
            )
            return False

        if f"serviceAccount:{self.trusted_service_account}" in role_bindings:
            _LOGGER.debug(
                f"[is_trusting_project] ServiceAccount {self.trusted_service_account} has permissions on project {project_id}"
            )
            return True
        else:
            _LOGGER.debug(
                f"[is_trusting_project] ServiceAccount {self.trusted_service_account} has no permissions on project {project_id}"
            )
            return False

    def _check_exclude_project(self, project_id):
        for exclude_project_id in self.exclude_projects:
            if fnmatch.fnmatch(project_id, exclude_project_id):
                _LOGGER.debug(
                    f"[check_exclude_project] Project {project_id} matched exclude pattern: {exclude_project_id}"
                )
                return False
        _LOGGER.debug(
            f"[check_exclude_project] Project {project_id} passed exclude check"
        )
        return True
