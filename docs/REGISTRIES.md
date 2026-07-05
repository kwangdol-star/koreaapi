# MCP 레지스트리 등재 체크리스트 (운영자용)

에이전트 세계의 "백링크" = 레지스트리 등재. 에이전트/개발자가 KoreaAPI를 **발견**하는 통로다.
아래 순서대로 하면 된다 — 전부 브라우저에서 가능. (제출 문구는 맨 아래 "복붙 블록" 사용.)

## 0. 선행 1회 — PyPI 배포 (uvx 설치 경로 활성화)
레지스트리들이 선호하는 설치법(`uvx --from koreaapi-mcp koreaapi-mcp`)은 패키지가 PyPI에 있어야 한다.
1. https://pypi.org 계정 생성 → Account settings → **API tokens** → 토큰 생성(복사).
2. GitHub `kwangdol-star/koreaapi` → Settings → Secrets and variables → **Actions** →
   New repository secret → 이름 `PYPI_API_TOKEN`, 값 = 토큰.
3. Actions 탭 → **publish** 워크플로 → Run workflow.
4. 확인: https://pypi.org/project/koreaapi-mcp/ 페이지가 생기면 성공.
   (실패 시 로그를 Claude 세션에 붙여넣으면 해결해 준다.)

## 1. Smithery — https://smithery.ai (최우선)
가장 큰 MCP 레지스트리. 레포에 `smithery.yaml`이 이미 준비돼 있다.
1. GitHub 계정으로 로그인 → **Add/Submit server** → `kwangdol-star/koreaapi` 지정.
2. 스키마 검증에서 걸리면 에러 메시지를 세션에 붙여넣기 (yaml은 준비됨, 스키마가 가끔 바뀜).

## 2. mcp.so — https://mcp.so
디렉터리형. **Submit** → GitHub URL 제출 + 설명 붙여넣기(아래 복붙 블록). 끝.

## 3. PulseMCP — https://www.pulsemcp.com
디렉터리형. Submit/Add server → GitHub URL + 설명. 자동 크롤링되기도 하지만 직접 제출이 빠르다.

## 4. Glama — https://glama.ai/mcp/servers
GitHub 공개 레포를 자동 인덱싱하는 편. 등재 안 보이면 사이트의 add/claim 경로로 제출.

## 5. awesome-mcp-servers (GitHub 리스트)
https://github.com/punkpeye/awesome-mcp-servers — PR 필요라 난이도 높음.
원하면 Claude 세션에서 PR 문안까지 만들어 준다 (제출은 계정 주인이).

---

## 복붙 블록 (제출 폼용)

**Name**: KoreaAPI

**Short description (EN)**:
> The verifiable data layer for Korean culture — 1,200+ cross-verified entities
> (K-pop, dramas, films, food, places, festivals …) with provenance + a Skill Score
> on every record. 11 read-only tools incl. Answer Products (canonical-name,
> fact-check, identity-resolve). No API key required.

**Categories/Tags**: `data` `knowledge` `korea` `k-pop` `entertainment` `verification` `aeo`

**Repository**: https://github.com/kwangdol-star/koreaapi
**Homepage**: https://kwangdol-star.github.io/koreaapi/
**Install (stdio)**: `uvx --from koreaapi-mcp koreaapi-mcp`  (또는 `pip install koreaapi-mcp` 후 `koreaapi-mcp`)

**Why it's trustworthy (심사 문구)**:
> Every record is cross-verified across independent sources (Wikidata, Wikipedia,
> MusicBrainz, TMDB, OpenStreetMap), carries machine-readable provenance + a 0–1
> Skill Score, and is tamper-evident (per-record SHA-256 + dataset hash chain).
> Tools are read-only; no secrets needed.

---

## 등재 후 확인
- 각 레지스트리 페이지가 생기면 URL을 세션에 알려주기 → `/for-agents`·`agents.json`에
  "찾을 수 있는 곳"으로 역링크 추가(발견 루프 완성).
- 주기 점검은 필요 없음 — 레포/패키지가 갱신되면 대부분 자동 반영.
