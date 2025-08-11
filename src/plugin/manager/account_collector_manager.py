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
        self.processed_project_ids = (
            set()
        )  # 변경점 1: 처리된 프로젝트 ID를 추적하기 위한 set 추가

    def sync(self) -> list:
        # 변경점 2: 시작 시 모든 활성(active) 프로젝트를 가져오기
        #   1. 서비스 계정이 접근할 수 있는 모든 조직을 발견
        #   2. 어떤 조직에도 속하지 않는 프로젝트를 찾음
        all_projects_info = self.resource_manager_v1_connector.list_projects(
            filter="lifecycleState:ACTIVE"
        )
        # _LOGGER.debug(f"Searching for projects. {all_projects_info}")

        # 변경점 3: 단일 조직이 아닌 *모든* 조직을 찾는 새로운 메서드로 변경
        organizations_info = self._get_organizations_info(all_projects_info)

        _LOGGER.debug(f"Searching for organizations. {organizations_info}")

        dq = deque()
        if organizations_info:
            visited = set()  # 변경점 4: 계층 구조 순회를 위한 'visited' set 추가 수집기가 동일한 폴더나 조직을 두 번 이상 처리하는 것을 방지하여 불필요한 API 호출과 잘못 구성된 환경에서의 잠재적인 무한 루프를 막음
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
                # _LOGGER.debug(f"Searching for folders. {folders_info}")
                for folder_info in folders_info:
                    folder_id = folder_info["name"].split("/")[-1]
                    if folder_id in self.exclude_folders:
                        continue
                    folder_name = folder_info["displayName"]
                    folder_parent = folder_info["name"]

                    # 변경점 5: location 리스트 생성 로직 단순화 존 코드는 불필요하고 비효율적인 `copy.deepcopy()`를 사용 간단한 리스트 연결(+) 연산으로 새 리스트를 생성하여 더 깔끔한 코드로 동일한 목표를 달성
                    next_locations = current_locations + [
                        {"name": folder_name, "resource_id": folder_parent}
                    ]
                    dq.append((folder_parent, next_locations))

        # 변경점 6: 조직이 없는 프로젝트를 처리하는 로직 추가 기존 코드는 조직 아래에 있지 않은 모든 프로젝트를 완전히 무시
        _LOGGER.info("Searching for projects without an organization.")
        no_org_projects = [
            p
            for p in all_projects_info
            if not p.get("parent") and p["projectId"] not in self.processed_project_ids
        ]
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
        # 변경점 8: try-except 블록 추가 오류를 포착하고 로그를 남긴 후, 다른 리소스에 대한 동기화 작업을 계속할 수 있게 함

        try:
            projects_info = self.resource_manager_v3_connector.list_projects(parent)
            active_projects = [p for p in projects_info if p.get("state") == "ACTIVE"]

            for project_info in active_projects or []:
                project_id = project_info["projectId"]

                if project_id in self.processed_project_ids:
                    _LOGGER.debug(
                        f"[sync] Skipping already processed project: {project_id}"
                    )
                    continue

                if not self._check_exclude_project(project_id):
                    _LOGGER.debug(f"[sync] Skipping excluded project: {project_id}")
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
                    # 프로젝트 ID를 set에 추가하여 다시 처리되는 것을 방지합니다.
                    self.processed_project_ids.add(project_id)

        except Exception as e:
            _LOGGER.error(f"[sync] Failed to list projects under {parent} => {e}")
            return

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
        # 변경점 9: 더 Pythonic하고 간결하게 리팩토링 기존의 'for' 루프를 `any()`와 제너레이터 표현식을 사용하여 더 읽기 쉽고 효율적인 코드로 대체 한 줄로 동일한 결과를 얻을 수 있음
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
