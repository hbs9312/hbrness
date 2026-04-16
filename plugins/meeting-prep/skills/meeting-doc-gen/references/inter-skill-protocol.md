# 중간 포맷 정의서 (Inter-Skill Protocol)

스캐너 스킬들이 출력하고 meeting-doc-gen이 소비하는 중간 포맷을 정의한다.
이 포맷이 스킬 간 계약(contract) 역할을 한다.

## 중간 포맷 목록

| 중간 포맷 | 생산자 | 소비자 | 저장 위치 |
|----------|--------|--------|----------|
| spec-analysis.md | spec-scanner | meeting-doc-gen | `{output_path}/spec-analysis.md` |
| impl-analysis.md | impl-scanner | meeting-doc-gen | `{output_path}/impl-analysis.md` |

## 계약 규칙

1. 스캐너 스킬이 변경되더라도 중간 포맷만 유지되면 나머지 컴포넌트는 수정 없이 동작한다.
2. 중간 포맷의 상세 스키마는 각 스킬의 SKILL.md "출력 포맷" 섹션을 참조한다.
3. 포맷 변경 시 모든 관련 스킬의 SKILL.md를 함께 업데이트해야 한다.
