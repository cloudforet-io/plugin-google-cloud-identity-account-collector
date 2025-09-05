# Google Cloud Identity Account Collector - 싱크 옵션 가이드

## 개요

Google Cloud Identity Account Collector는 Google Cloud 조직 내의 프로젝트와 폴더를 재귀적으로 탐색하여 계정 정보를 수집하는 플러그인입니다. 이 문서는 싱크 옵션의 용법과 처리 로직을 설명합니다.

## 싱크 옵션 목록

### 1. trusting_organization
- **타입**: `boolean`
- **기본값**: `true`
- **설명**: 조직 레벨에서 서비스 계정을 신뢰하는지 여부
- **처리 로직**:
  - `true`: 모든 프로젝트를 수집 (조직 레벨 권한으로 간주)
  - `false`: 각 프로젝트별로 IAM 권한을 확인하여 수집

### 2. exclude_projects
- **타입**: `array`
- **기본값**: `[]`
- **설명**: 수집에서 제외할 프로젝트 ID 패턴 목록
- **처리 로직**: Unix filename pattern matching을 사용하여 프로젝트 ID와 매칭
- **예시**: `['sys-*', 'temp-*', 'dev-*']`

### 3. exclude_folders
- **타입**: `array`
- **기본값**: `[]`
- **설명**: 수집에서 제외할 폴더 ID 목록
- **처리 로직**: 폴더 ID를 문자열로 변환하여 정확히 매칭
- **예시**: `['123456789', '987654321']`

### 4. start_depth
- **타입**: `integer`
- **기본값**: `0`
- **최소값**: `0`
- **설명**: 프로젝트 수집을 시작할 깊이 레벨
- **처리 로직**:
  - `0`: 조직 레벨부터 모든 프로젝트와 폴더 수집
  - `1`: 첫 번째 레벨 폴더부터 수집 (조직 레벨의 프로젝트는 제외)
  - `2`: 두 번째 레벨 폴더부터 수집
  - `n`: n번째 레벨 폴더부터 수집

### 5. include_location_from_depth
- **타입**: `integer`
- **기본값**: `start_depth` 값과 동일
- **최소값**: `0`
- **설명**: 프로젝트의 경로 정보에 폴더 위치를 포함하기 시작할 깊이 레벨
- **처리 로직**:
  - 지정된 깊이 이전의 폴더는 프로젝트 경로에 포함되지 않음
  - 지정된 깊이부터의 폴더만 프로젝트의 `location` 필드에 포함됨
  - `start_depth`보다 클 수 없음

## 처리 로직

### 1. BFS (Breadth-First Search) 탐색
```
1. Organization에서 시작 (depth 0)
   ↓
2. 각 노드 처리:
   ├── 프로젝트 수집 조건 확인 (current_depth >= start_depth)
   │   ├── 조건 만족: 프로젝트 수집 실행
   │   └── 조건 불만족: 프로젝트 수집 건너뛰기
   │
   └── 하위 폴더 탐색:
       ├── 폴더 목록 조회
       ├── 각 폴더에 대해:
       │   ├── 방문 기록 확인 (무한 루프 방지)
       │   ├── 제외 폴더 확인
       │   └── 위치 추적 조건 확인 (current_depth >= include_location_from_depth)
       │       ├── 조건 만족: 폴더 정보를 locations에 추가
       │       └── 조건 불만족: locations 유지
       └── 큐에 추가
   ↓
3. 다음 레벨 처리 (depth + 1)
```

### 2. 프로젝트 필터링
- **상태 필터**: ACTIVE 상태 프로젝트만 수집
- **제외 패턴**: `exclude_projects` 패턴 매칭으로 제외
- **폴더 제외**: `exclude_folders`에 포함된 폴더 내 프로젝트 제외
- **깊이 제어**: `start_depth`에 따라 수집 시작 깊이 제어

### 3. 권한 검증
- **조직 신뢰**: `trusting_organization=true`인 경우 모든 프로젝트 수집
- **프로젝트별 권한**: `trusting_organization=false`인 경우 프로젝트별 IAM 권한 확인

### 4. 성능 최적화
- **캐싱**: 폴더 목록(최대 100개), 프로젝트 목록(최대 50개) 캐시
- **무한 루프 방지**: 방문한 폴더 기록 (`visited_folders` set)
- **순차 처리**: BFS 레벨별 처리로 메모리 효율성 확보

## 사용 예시

### 기본 설정
```json
{
  "options": {
    "trusting_organization": true,
    "exclude_projects": [],
    "exclude_folders": [],
    "start_depth": 0
  }
}
```

### 고급 설정
```json
{
  "options": {
    "trusting_organization": false,
    "exclude_projects": ["sys-*", "temp-*"],
    "exclude_folders": ["123456789"],
    "start_depth": 2,
    "include_location_from_depth": 2
  }
}
```

## 시작깊이와 인클루드 로케이션 예제

### 예제 1: start_depth=1, include_location_from_depth=1

**설정:**
```json
{
  "options": {
    "start_depth": 1,
    "include_location_from_depth": 1
  }
}
```

**동작:**
- 깊이 1부터 프로젝트 수집 시작 (조직 레벨의 프로젝트는 제외)
- 깊이 1부터 폴더 경로 추적 시작

**결과:**
```
수집된 프로젝트:
- Project 1: location=[{"name": "Folder A-1", "resource_id": "folders/456"}]
- Project 2: location=[{"name": "Folder A-1", "resource_id": "folders/456"}]
- Project 3: location=[{"name": "Folder A-2", "resource_id": "folders/789"}]
- Project 4: location=[{"name": "Folder B-1", "resource_id": "folders/012"}]

제외된 프로젝트:
- Organization 레벨의 프로젝트들 (깊이 0)
```

### 예제 2: start_depth=2, include_location_from_depth=1

**설정:**
```json
{
  "options": {
    "start_depth": 2,
    "include_location_from_depth": 1
  }
}
```

**동작:**
- 깊이 2부터 프로젝트 수집 시작 (조직 레벨과 첫 번째 레벨의 프로젝트는 제외)
- 깊이 1부터 폴더 경로 추적 시작 (깊이 1의 폴더부터 경로에 포함)

**결과:**
```
수집된 프로젝트:
- Project 1: location=[{"name": "Folder A", "resource_id": "folders/123"}, {"name": "Folder A-1", "resource_id": "folders/456"}]
- Project 2: location=[{"name": "Folder A", "resource_id": "folders/123"}, {"name": "Folder A-1", "resource_id": "folders/456"}]
- Project 3: location=[{"name": "Folder A", "resource_id": "folders/123"}, {"name": "Folder A-2", "resource_id": "folders/789"}]
- Project 4: location=[{"name": "Folder B", "resource_id": "folders/321"}, {"name": "Folder B-1", "resource_id": "folders/012"}]

제외된 프로젝트:
- Organization 레벨의 프로젝트들 (깊이 0)
- Folder A, Folder B 레벨의 프로젝트들 (깊이 1)

경로 정보:
- 깊이 1의 폴더(Folder A, Folder B)부터 location에 포함됨
- 깊이 2의 폴더(Folder A-1, Folder A-2, Folder B-1)도 location에 포함됨
```

## 폴더 구조 예시

```
Organization (depth 0)
├── Folder A (depth 1)
│   ├── Folder A-1 (depth 2)
│   │   ├── Project 1 (depth 3)
│   │   └── Project 2 (depth 3)
│   └── Folder A-2 (depth 2)
│       └── Project 3 (depth 3)
└── Folder B (depth 1)
    └── Folder B-1 (depth 2)
        └── Project 4 (depth 3)
```

### 설정별 결과

#### start_depth=2, include_location_from_depth=2
```
수집된 프로젝트:
- Project 1: location=[{"name": "Folder A-1", "resource_id": "folders/456"}]
- Project 2: location=[{"name": "Folder A-1", "resource_id": "folders/456"}]
- Project 3: location=[{"name": "Folder A-2", "resource_id": "folders/789"}]
- Project 4: location=[{"name": "Folder B-1", "resource_id": "folders/012"}]
```

#### start_depth=3, include_location_from_depth=2
```
수집된 프로젝트:
- Project 1: location=[{"name": "Folder A-1", "resource_id": "folders/456"}]
- Project 2: location=[{"name": "Folder A-1", "resource_id": "folders/456"}]
- Project 3: location=[{"name": "Folder A-2", "resource_id": "folders/789"}]
- Project 4: location=[{"name": "Folder B-1", "resource_id": "folders/012"}]
```

## 에러 처리

### 유효성 검증
```python
if include_location_from_depth > start_depth:
    raise ValueError(
        f"include_location_from_depth ({include_location_from_depth}) "
        f"cannot be greater than start_depth ({start_depth})"
    )
```

### 권한 에러
- 조직 접근 권한 없음: 즉시 종료
- 폴더 검색 권한 없음: 즉시 종료
- 상세한 에러 메시지 제공

## 주의사항

1. **서비스 계정 권한**: Resource Manager API 접근 권한 필요
2. **API 할당량**: 대규모 조직의 경우 API 할당량 고려
3. **성능**: 순차 처리로 인해 대규모 조직에서는 시간이 오래 걸릴 수 있음
4. **보안**: 서비스 계정 키는 안전하게 관리해야 함

## 제한사항

1. **병렬 처리 없음**: 순차적으로 처리되어 성능 제한
2. **캐싱 제한**: 요청 내에서만 캐싱, 세션 간 캐싱 없음
3. **제한적인 필터링**: 프로젝트/폴더 제외만 지원
4. **에러 재시도 없음**: API 실패 시 재시도 로직 없음
