# KoreaAPI — Design Heritage

> 디자인 헤리티지 = 브랜드의 시각적 도리(道理). 새로 만드는 모든 페이지·뱃지·컴포넌트는
> 이 문서에 비추어 검증한다. 여기 적힌 값은 전부 코드에 실재하는 토큰이다 —
> `src/koreaapi/admin.py`(사이트 생성기)·`src/koreaapi/badge.py`(뱃지)에서 그대로 인용.

## 한 줄 정의
**태극기(정통성) × 검증된 신뢰(gold) × 리퀴드 글래스(현대적 재질).**
차가운 실리콘밸리 다크가 아니라 **따뜻한 옻칠 위의 금(金)** 위에, 사실을 얹는
반투명 "검증 유리판". 장식이 아니라 — **신뢰 해자를 눈에 보이게 렌더한 것**이다.

---

## 세 갈래 혈통 (The three ancestries)

### 1. 태극기 — 문자 그대로의 유산
브랜드 마크는 "한국 느낌"이 아니라 **실제 태극기를, 법대로 그린 것**이다.
`_FLAG`(admin.py:1206)은 **국기법 시행령**의 작도법을 주석에 명시하고 그린다: 깃발 3:2,
태극 지름 = 높이/2, 4괘(건·곤·감·리)는 6×4.4 블록 중심이 대각선 위 flag-centre에서
11.2 지점에 앉는다.

| 요소 | 값 | 의미 |
|---|---|---|
| 태극 red | `#cd2e3a` | 양(陽) |
| 태극 blue | `#0047a0` | 음(陰) |
| 바탕 | `#fff` | 백의(白衣) |
| 4괘 | `#000` | 건곤감리 |

- `.dot`(admin.py:1101) — 헤더의 회전점은 태극 conic-gradient 스피너(`taegeuk 3.6s linear infinite`).
  로딩 인디케이터조차 국기다.
- 이 정확성이 곧 제품 철학이다: **우리는 대충 그리지 않는다 = 우리는 대충 검증하지 않는다.**
  마크의 작도 정밀도가 데이터의 교차검증 정밀도를 은유한다.

### 2. 금(金) on 온(溫) 다크 — 전통 안료의 계승
팔레트는 차가운 회색 다크가 아니라 **따뜻한 near-black(#0D0B06) 위의 금박**이다.
단청·나전·옻칠 위 금장식의 독법 — 어둡되 차갑지 않고, 빛나되 요란하지 않다.

### 3. 리퀴드 글래스 — 신뢰 제품의 현대적 재질
모든 카드·표·인용 블록은 반투명 유리판(glassmorphism) 위에 놓인다. *신뢰* 제품에
유리를 쓰는 이유: **사실은 그 뒤의 출처(provenance)가 비쳐 보여야 한다.** 불투명 상자가
아니라 검증 과정이 들여다보이는 판.

---

## 색 토큰 (Color tokens · `:root`, admin.py:1086)

| 토큰 | 값 | 용도 |
|---|---|---|
| `--bg` | `#0D0B06` | 바탕 (온-다크) |
| `--panel` / `--panel2` | `#17120A` / `#1E1710` | 패널 표면 |
| `--line` | `#3A2F1A` | 따뜻한 경계선 |
| `--ink` | `#F7F2E8` | 본문 (웜 오프화이트) |
| `--mut` | `#C2B7A3` | 보조 텍스트 (taupe) |
| `--dim` | `#8C8068` | 흐린 텍스트 (romanization·footer) |
| `--accent` | `#E9C46A` | **시그니처 골드** (링크·강조·아이콘 stroke) |
| `--accent2` | `#D9A441` | 딥 골드 (그라디언트 짝) |
| `--ok` | `#10B981` | 신선/검증 통과 |
| `--bad` | `#EF4444` | 실패/stale |

**배경 글로우** — 상단 중앙 웜 앰버 radial:
`radial-gradient(1100px 520px at 50% -160px, #241A06 0%, --bg 58%)` + `background-attachment:fixed`.
애니메이션 오로라는 성능상 제거됨(`_AURORA=""`, admin.py:1245) — **정적 골드 + 글래스**로 확정.

---

## 재질 — 리퀴드 글래스 (Material tokens)

| 토큰 | 값 |
|---|---|
| `--glass` | `linear-gradient(135deg, rgba(255,255,255,.08), rgba(255,255,255,.02))` |
| `--gbord` | `rgba(255,255,255,.14)` |
| `--blur` | `saturate(170%) blur(18px)` (backdrop-filter) |
| `--gshadow` | 다층 drop-shadow + 안쪽 하이라이트(inset)로 만드는 "물유리" 입체 |

모든 유리 컴포넌트는 `backdrop-filter:var(--blur)`(+`-webkit-` 접두) 필수 — 배경 글로우가
판을 통과해 굴절돼야 재질이 산다.

---

## 타이포그래피 (Typography)

- **스택**(`_FONT_STACK`, admin.py:1243):
  `'Montserrat','Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic', system-ui, -apple-system, sans-serif`
- **라틴/제목 = Montserrat**(Google Fonts, wght 400–800), **한글 = 시스템 폰트 폴백**.
  근거: Montserrat엔 한글 글리프가 없다 → 무거운 한글 웹폰트를 싣지 않고 시스템 폴백으로
  브랜드 일관성 확보(admin.py:1235).
- **제목**: `font-weight:800; letter-spacing:-.02em` (타이트 디스플레이).
- **H2 = 아이브로 레이블**: `text-transform:uppercase; letter-spacing:.04em; color:--mut`.
- **이름 3단 규약** — 엔티티명은 세 줄로 계층화:
  - 공식명(en/ko) → `--ink`
  - `.ko` 한글 보조 → `--mut`
  - `.rom` 로마자 → `--dim` 12px
  이 tri-line이 "양국어 + 공식명" 원칙의 시각적 구현이다.

---

## 신뢰를 색으로 (Trust made legible)

색은 취향이 아니라 **검증 상태의 인코딩**이다. 이것이 이 디자인의 핵심 — 신뢰 해자가
스캔 한 번에 읽힌다.

**Skill Score → 색**(admin.py:953, 3578):

| 구간 | 색 |
|---|---|
| high ≥ 0.8 | `#10B981` (green) |
| medium 0.5–0.8 | `#F59E0B` (amber) |
| low < 0.5 | `#EF4444` (red) |
| cross-verified (≥2 sources) | `#E9C46A` (gold) |

**신선도 → 색**: `.fresh` `#10B981` / `.stale` `#EF4444` (freshness 해자를 색으로).
**인용 블록** `.cite` — 골드 틴트 유리(`rgba(233,196,106,.16)` 그라디언트 + 골드 테두리):
"이대로 인용하라"는 한 줄을 시각적으로 격상.

---

## 임베드 뱃지 (The viral citation artifact · badge.py)

shields.io 스타일, **완전 self-contained SVG**(폰트·네트워크 없음). 누구나 `<img>`로 걸면
백링크 + "via KoreaAPI" 마크 → 퍼질수록 KoreaAPI가 인용 표준의 셸링 포인트가 된다.

| Tier | 색 | 라벨 | 틱 |
|---|---|---|---|
| officially-certified | `#7C3AED` violet | certified | ✓ |
| triple-cross-verified | `#10B981` green | triple-verified | ✓✓✓ |
| cross-verified | `#2563EB` blue | cross-verified | ✓ |
| single-source | `#9CA3AF` grey | single-source | ✓ |
| unverified | `#EF4444` red | not found | ✗ |

- 왼쪽 플레이트 `#24292e`(깃허브 다크), 오른쪽이 tier 색. 등급이 높을수록(정식 인증=보라)
  "블루체크"처럼 읽힌다.
- **정직성 원칙**: single-source는 회색으로 "미교차검증"임을 숨기지 않는다. 뱃지는 과장하지 않는다.

---

## 아이콘 (Iconography)

- 이모지 대신 **라인 스트로크 SVG**(`_icon`, admin.py:1252): 골드 stroke `#E9C46A`,
  `stroke-width:1.7`, `stroke-linecap/join:round`, em 단위. 어느 표면에서도 일관되게 읽힘.
- `_ICON` 세트가 섹션·허브·pill 라벨의 이모지를 대체(artist=마이크 등).

---

## 컴포넌트 사전 (Component lexicon)

| 클래스 | 형태 | 역할 |
|---|---|---|
| `.pill` | 완전 라운드(999px) 유리 | 최상단 내비 |
| `.chip` / `.pchip` | radius 10px 유리 | 필터·엔티티 칩(`.pchip`는 hover 시 골드 테두리 + `translateY(-1px)` 리프트) |
| `.card` | radius 18px 유리 | 통계/요약 카드 |
| `.note` | 유리 + `border-left:3px solid --accent` | 골드 레일 안내문 |
| `.qa` | 유리 카드 | AEO Q&A(답변 엔진이 들어올리는 블록) |
| `.cite` | 골드 틴트 유리 | 인용 라인 |
| `.badge` | 컬러 배경 + `#06140E` 다크 텍스트, weight 800 | Skill Score 뱃지 |
| `.tablewrap` | radius 18px 유리 + `overflow-x:auto` | 반응형 표 컨테이너 |

**레이아웃 폭**: 엔티티 리딩 페이지 `max-width:860px`, 허브/리스트 `1180px`.
기본 패딩 `34px 20px 52px`.

---

## 양국어는 법이다 (Bilingual by construction)

- 모든 답변 페이지는 EN + `/ko` 짝을 hreflang parity로 함께 낸다. 한국어 페이지가 영어의
  축소판이 아니라 **동일한 해자(검증 이력·타임스탬프·인용)를 그대로** 노출한다.
- 검증 이력 라벨도 이중: "tracked since / Verification history" ↔ "부터 추적 / 검증 이력".
- 이는 `test_frontend_integrity.py`·`test_history.py`가 강제한다(디자인이 곧 테스트).

---

## 불변식 (Design invariants — 바꾸지 말 것)

**DO**
- 색으로 검증 상태를 인코딩한다(Skill/freshness/tier). 색은 정보다.
- 태극기 마크는 국기법 작도를 지킨다. 임의 변형 금지.
- 유리 컴포넌트엔 항상 `backdrop-filter` + `-webkit-` 접두를 함께.
- 이름은 3단(공식/한글/로마자) 계층으로.
- EN/`/ko` parity 유지 — 한쪽만 늘리지 않는다.

**DON'T**
- 차가운 순수 그레이 다크(#000/#111 계열)로 바탕을 바꾸지 않는다 — 웜 다크가 정체성.
- 골드(`#E9C46A`)를 임의 색조로 교체하지 않는다 — 시그니처.
- 무거운 한글 웹폰트를 싣지 않는다 — 시스템 폴백이 의도.
- 뱃지에서 등급을 부풀리지 않는다 — single-source는 회색.
- 성능을 해치는 배경 애니메이션을 되살리지 않는다(정적 골드+글래스가 확정).

---

## 코드 위치 (Where it lives)

| 자산 | 파일:라인 |
|---|---|
| 색·재질 토큰(`:root`) | `src/koreaapi/admin.py:1086` |
| 태극기 마크 `_FLAG` | `src/koreaapi/admin.py:1206` |
| 태극 스피너 `.dot` | `src/koreaapi/admin.py:1101` |
| 폰트 링크·스택 | `src/koreaapi/admin.py:1238`(`_FONT_LINKS`)·`:1243`(`_FONT_STACK`) |
| 라인 아이콘 `_icon`/`_ICON` | `src/koreaapi/admin.py:1252` |
| Skill Score 색 함수 | `src/koreaapi/admin.py:953` |
| 임베드 뱃지(tier→색) | `src/koreaapi/badge.py` |
| 프런트 무결성 테스트 | `tests/test_frontend_integrity.py` |

> 이 문서는 관찰된 코드 토큰의 서술이다. 토큰을 바꾸면 이 문서도 같은 커밋에서 갱신한다 —
> 헤리티지와 구현이 어긋나는 순간 둘 다 신뢰를 잃는다.
