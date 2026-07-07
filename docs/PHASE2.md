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
