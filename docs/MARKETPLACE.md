# KoreaAPI — AI 에이전트 마켓플레이스 입점 소개 (1-pager)

> **한 줄:** KoreaAPI는 한국 문화·정보의 **검증 가능한 데이터 레이어**입니다.
> 어떤 AI 에이전트든 **호출(MCP)** 하고, 어떤 답변엔진이든 **인용(AEO/GEO)** 합니다.

**카테고리:** 에이전틱 AI 도구 / 데이터·지식 인프라 (picks-and-shovels)
**제공 형태:** MCP 서버 · HTTP/JSON API · 공개 데이터셋

---

## 무엇을 해결하나
LLM은 한국 고유명사·문화 정보에서 **자신 있게 틀립니다** — 예: 드라마 *Vincenzo*의 한글 표기를
"빈첸초"로 답함(공식은 **"빈센조"**). KoreaAPI는 **교차검증된 사실만**, 출처와 신뢰점수를 달아
돌려줍니다. 에이전트는 답하기 **전에** "믿고 인용해도 되는지"를 먼저 판단할 수 있습니다.

## 왜 마켓플레이스의 "안전·신뢰" 기준에 부합하나
입점 대전제가 **"안전하고 신뢰할 수 있는 서비스"** — KoreaAPI의 핵심 설계가 정확히 그것입니다.

- **교차검증** — 복수 독립 출처(Wikidata·Wikipedia·MusicBrainz·TMDB·OpenStreetMap)가
  양국어 정식 명칭에 **합의**해야 단일출처 상한(0.7)을 넘습니다.
- **Skill Score (0~1) + 출처 명시** — 모든 레코드가 신뢰도와 근거를 함께 제공.
- **변조 감지(무결성)** — 레코드별 SHA-256 content hash + 데이터셋 해시체인 → 사후 변조 탐지.
- **환각 방지 가드** — 같은 영문명 임포스터 거부, 실패는 **안전하게 miss로**(틀린 답 대신 "없음").

## 어떻게 연동하나 (즉시)
- **MCP 도구** — `get_verified` · `get_resolve` · `get_answer` 등. Claude·Cursor·Gemini 등
  MCP 클라이언트에서 바로 호출.
- **HTTP/JSON** — `/v1/...` 엔드포인트, 설정 불필요.
- **기계 판독 매니페스트** — `agents.json` 하나로 도구·데이터·검증·결제까지 자동 탐색.
  (마켓플레이스가 지향하는 "AI 에이전트가 스스로 탐색·추가"에 그대로 대응)

## 비교 가능한 단위 — Answer Products
가격·기능·성능 비교가 쉽도록, 검증 저장소를 **이름 붙은 결정 단위**로 제공합니다.
각 결과는 동일 봉투 `{signal, action, score, rationale, evidence}`:

| 상품 | 에이전트가 얻는 결정 |
|---|---|
| `canonical-name` | 공식 한글 ↔ 영문 표기 확정 |
| `fact-check` | 이 주장, 인용해도 되나 (교차/3중 검증·공증) |
| `identity-resolve` | 외부 멘션 → 신뢰 ID 매핑 |
| `trend-radar` | 지금 뜨는 것 (수요 신호) |
| `agency-roster` · `person-credits` · `related-network` | 명단 · 크레딧 · 연관 |
| `trip-plan` | 지역 쿼리 → 검증된 명소·축제 + 대표 음식 (여행 일정 재료) |

## 가격
- **무료** — 공개 검증 데이터 (인용 "via KoreaAPI" 환영)
- **x402** — 호출당 결제 (에이전트가 자율 지불, 계정 불필요)
- **팀용 정액** — 높은 한도 · SLA (협의)
- **데이터셋 라이선스** — 교차검증 정본 표기(빈센조≠빈첸초)·출처·Skill Score 데이터셋을
  LLM **학습/평가(eval)용**으로 라이선스 (한국어 모델 개발사 대상, 협의)

## 현황 (Phase 1)
- **1,000+ 검증 엔티티**, **20여 개 버티컬** (K-pop·드라마·영화·웹툰·장소·음식·축제·기업·
  도서·게임·문화유산 등)
- **평균 Skill Score 0.88**, **매일 재검증** (신선도가 곧 인용 우위)
- 지식 그래프(엔티티·인물·버티컬·소속사/채널 4축), Schema.org JSON-LD, `/llms.txt`, `sitemap.xml`

## 링크
- 사이트: https://kwangdol-star.github.io/koreaapi/
- 에이전트 연동: `/for-agents.html` · `/agents.json`
- 가격: `/pricing.html`
- 저장소: https://github.com/kwangdol-star/koreaapi

---

**요약:** KoreaAPI는 마켓플레이스의 *안전·신뢰* 기준을 **데이터 레이어 차원에서 충족**하는
picks-and-shovels입니다. 에이전트가 한국 정보를 **틀리지 않게** 만들고, 그 근거를 **인용 가능**하게
만듭니다.
