# Phase 2 — 크로스체크 소스 확장 계획 (소외 버티컬 보충)

## 현재 소스 지도 (정직 버전)
| 강함 (3소스+) | artist(위키2+MusicBrainz) · drama/film/animation(+TMDB) · place(+OSM+KTO정부) · region(+KOSIS정부) |
|---|---|
| **소외 (위키 2개뿐)** | **food · webtoon · book · classic · game · company · brand · sports · song · actor · university · medical · festival · heritage** |
| 이름앵커(설계상 OK) | folklore · history · concept |

## 추가 소스 — 우선순위 (운영자 부담 기준)

**Tier A — 새 키 불필요, 코드만 (다음 빌드 세션에서 일괄):**
1. **KTO TourAPI → festival: 확장** — searchFestival 엔드포인트, 키 이미 있음 → 축제에 정부 출처+일정.
2. **TMDB → actor: 확장** — person API, 키 이미 있음 → 배우 제3소스+필모.
3. **MusicBrainz → song: 확장** — recording 검색, 무키 → 곡 제3소스.
4. **Open Library → book: 신규** — openlibrary.org, 무키 → 도서 제3소스(ISBN/서지).

**Tier B — 공공데이터포털 무료키 (형 발급 1회, KOSIS와 같은 dormant 패턴):**
5. **국가유산청 API → heritage:** — 문화유산에 정부 공식 지정정보. 신뢰 서사 최상급.
6. **심평원 병원정보 → medical:** — 병원 정부 등록정보.
7. **DART 공시 → company:** — 국내 기업 공식 공시 = 기업 버티컬의 정부 티어.

**Tier C — 그다음:**
8. RAWG(game, 무료키) · TheSportsDB(sports, 무키) · AniList(webtoon/만화, 무키 GraphQL)
9. **Wiktionary → proverb:/slang: 신규 버티컬** — 속담·관용구·은어 (등재 항목만, 검증 원칙 유지)
10. 온체인 앵커링 (보류분)

## 언제 (게이트 조건)
Phase 2 착수는 **다음 둘이 확인되면**:
1. 현행 파이프라인 안정 — collect 2~3회 연속: 오프셋 사다리 +N 재개 · audit 0 위반 · concept 18종 인제스트 · 새 도메인 canonical 정상.
2. **Smithery 등재 완료** (발견 표면 먼저 — 소스 늘리기보다 트래픽 통로가 우선).

예상 작업량: Tier A = 세션 1회(어댑터 4확장, 오프라인 픽스처 테스트 포함) · Tier B = 키 발급 후 세션 1회 · Tier C 순차.

## 원칙 재확인
새 소스도 전부: 파스 순수함수+픽스처 테스트 / 이름·타입 가드 통과분만 / 키는 dormant 패턴 / 실패는 miss.

---

## 사례 조사 부록 시사점 → Phase 2 조정 (2026.7)
카트리지 사례집에서 **KoreaAPI에 직접 해당**하는 것만 추림. (NHS×팔란티어·구글 나이팅게일·
IBM 왓슨·온프레미스 신뢰 = 형제 카트리지 사업 몫 → 우리 판단엔 섞지 않음.)

1. **Scale AI ($14.3B, 데이터 '가공'만으로) = 우리 정체성 확증.** 소유한 회사가 아니라
   정제·검증·구조화하는 회사가 가장 비싸게 팔렸다. KoreaAPI = 한국 문화 데이터의 **검증·정제
   레이어** — 위키 원본을 소유할 필요가 없다. 포지셔닝 한 줄: "한국 문화 데이터의 Scale AI".
2. **"검증된 전문 문서가 가장 비싸게 팔린다" (Wiley·Bloomberg·Tempus) → 우선순위 재조정.**
   볼륨(무키 취미 소스)보다 **권위(정부 출처)**가 값을 만든다 → Tier B를 Tier C 위로, 그리고
   Tier A 직후 **국가유산청→heritage 1건을 먼저** (문화유산 = 간판, 정부 지정 = 최강 배지, 논란 0).
3. **어트리뷰션·출처가 의무가 되는 중 (Stack Overflow 출처표기·유튜브 옵트인·Getty).** 우리의
   레코드별 provenance + content hash + cite 라인이 시장이 강제하는 방향 → 레코드에 **명시적
   license 필드** 노출(작업 작음, 신뢰의 상품화).
4. **"국내엔 아직 AI 학습 기준 계약이 없다" (네이버 vs 신문협회) = 선점 공백.** 데이터셋
   라이선스·평판 레인용 **표준 계약 템플릿**(AP식 리셋 조항 + Getty식 반복 인세 + 하퍼콜린스식
   출력 가드레일)을 먼저 공개하면 기준을 갖는다 → REPUTATION/데이터셋 레인 후속 문서.

**조정된 Phase 2 순서:** Tier A(무키 4개) → **국가유산청→heritage**(정부 배지 우선)
→ 나머지 Tier B(DART·심평원) → Tier C.
