# security-contest-bot

여러 사이트에서 정보보안 관련 공모전·대회 글을 주기적으로 수집해, 새로 올라온 것만 디스코드 채널에 웹훅으로 알려주는 봇입니다.

## 동작 방식

```
사이트 수집 → 제목 키워드 필터 → seen.json과 대조해 새 항목만 추림 → 디스코드 Embed 전송 → seen.json 갱신
```

### 최초 실행은 조용히 지나갑니다

`seen.json`이 비어 있는 첫 실행에서는 **알림을 보내지 않고** 현재 걸린 항목들을 기준점으로 기록만 합니다. 그러지 않으면 첫 실행에서 30건 넘는 알림이 한꺼번에 쏟아집니다.

```
최초 실행입니다. 알림을 보내지 않고 현재 35건을 기준점으로 기록합니다.
```

그 다음 실행부터 새로 올라온 글만 알림이 갑니다. 과거 글까지 전부 받고 싶으면 `config.BOOTSTRAP_ON_FIRST_RUN = False`로 바꾸세요.

GitHub Actions에서 **매일 1회(한국시간 낮 12시경, GitHub 부하에 따라 몇 분~몇십 분 지연될 수 있음)** 실행되는 서버리스 구조이고, 중복 알림 방지 상태(`data/seen.json`)는 워크플로우가 레포에 커밋백해서 유지합니다.

수집 대상:

| 모듈 | 사이트 | 방식 | 상태 |
| --- | --- | --- | --- |
| `boannews.py` | 보안뉴스 | requests + BeautifulSoup (EUC-KR) | 동작 검증됨 |
| `thinkcontest.py` | 씽굿 | requests + 내부 JSON API | 동작 검증됨 |
| `linkareer.py` | 링커리어 | requests + 공개 GraphQL API | 동작 검증됨 |
| `kisa_notice.py` | KISA 공지사항 | requests + BeautifulSoup | 동작 검증됨 |

**브라우저가 필요 없습니다.** 씽굿과 링커리어는 자바스크립트로 목록을 렌더링하지만,
브라우저 네트워크 탭으로 확인한 결과 두 사이트 모두 데이터를 인증 없이 호출 가능한
JSON API에서 받아옵니다. 그 API를 직접 호출하므로 Playwright와 chromium 설치가 필요 없고,
GitHub Actions 실행도 훨씬 가볍고 빠릅니다.

한 사이트가 실패해도 나머지 사이트 수집은 그대로 진행됩니다.

## 로컬 실행

```bash
# 1) 의존성 설치 (requests, beautifulsoup4 뿐입니다)
pip install -r requirements.txt

# 2) 웹훅 URL 설정
cp .env.example .env
#    .env를 열어 DISCORD_WEBHOOK_URL 값을 채웁니다.

# 3) 실행
python -m scraper.main
```

`.env`가 없거나 `DISCORD_WEBHOOK_URL`이 비어 있으면 **DRY-RUN 모드**로 동작합니다. 실제 전송 대신 아래처럼 출력만 하고, `seen.json`도 갱신하지 않습니다.

```
[DRY-RUN] would send: 엔키화이트햇, 국가 공급망 안정화 '선도 사업자' 선정
```

## 디스코드 웹훅 URL 만들기

1. 알림을 받을 채널에서 **채널 편집(톱니바퀴)** 클릭
2. **연동(Integrations)** → **웹훅(Webhooks)** → **새 웹훅**
3. 이름과 채널을 확인한 뒤 **웹훅 URL 복사**
4. 복사한 URL을 `.env`의 `DISCORD_WEBHOOK_URL`에, 또는 GitHub 시크릿에 넣습니다.

웹훅 URL은 사실상 비밀번호입니다. 절대 커밋하지 마세요 (`.env`는 `.gitignore`에 등록되어 있습니다).

## GitHub Actions 배포

1. 이 레포를 GitHub에 올립니다.
2. **Settings → Secrets and variables → Actions → New repository secret**에서
   이름 `DISCORD_WEBHOOK_URL`, 값에 웹훅 URL을 등록합니다.
3. **Actions** 탭에서 워크플로우를 활성화합니다. `workflow_dispatch`가 있으므로 **Run workflow** 버튼으로 즉시 수동 실행해 볼 수 있습니다.

### 실행 주기 바꾸기

`.github/workflows/notify.yml`의 cron 식을 수정합니다 (UTC 기준).

```yaml
on:
  schedule:
    - cron: "0 3 * * *"     # 매일 UTC 03:00 = 한국시간 낮 12:00 (현재 설정)
    # - cron: "0 */4 * * *" # 4시간마다
    # - cron: "0 0 * * *"   # 매일 UTC 00:00 (한국시간 09:00)
```

GitHub Actions의 예약 실행은 정시를 보장하지 않습니다. 러너 부하에 따라 몇 분에서 몇십 분까지 밀릴 수 있으니, 정확한 시각이 필요한 용도라면 `workflow_dispatch`로 수동 실행하세요.

### seen.json 커밋백

워크플로우 마지막 스텝이 `data/seen.json`을 커밋·푸시해서 다음 실행에서도 중복 알림이 방지됩니다. 변경사항이 없으면 커밋을 건너뜁니다. 이를 위해 워크플로우에 `permissions: contents: write`가 필요합니다 (이미 설정되어 있습니다).

## 새 사이트 추가하기

1. `scraper/sites/새사이트.py`를 만들고 `fetch_items() -> list[Item]`을 구현합니다.
   각 항목은 다음 형태여야 합니다.

   ```python
   {
       "id": "mysite-12345",       # 중복 판단 기준. URL이나 게시글 번호 기반으로 안정적으로
       "title": "게시글 제목",
       "url": "https://...",       # 절대 URL
       "source": "사이트 표시명",
       "published": "2026-07-22",  # 모르면 None
   }
   ```

   `scraper/sites/base.py`의 `make_item()` 헬퍼를 쓰면 필드 누락을 막을 수 있습니다.
   키워드 필터링은 `main.py`가 공통으로 처리하므로 어댑터에서는 하지 않습니다.

2. `scraper/main.py`에서 모듈을 import 하고 `SITES` 목록에 추가합니다.

   ```python
   from .sites import boannews, kisa_notice, linkareer, thinkcontest, 새사이트

   SITES = [boannews, kisa_notice, thinkcontest, linkareer, 새사이트]
   ```

## 설정값

`scraper/config.py`에서 수정합니다.

| 항목 | 설명 |
| --- | --- |
| `KEYWORDS` | 제목 필터 키워드. 대소문자 무시 부분일치 |
| `MAX_ITEMS_PER_SOURCE` | 소스별 1회 실행당 최대 신규 알림 건수 (보안뉴스 20, 씽굿 20, KISA 10, 링커리어 10). 뉴스 매체는 통과량이 많고 공모전 게시판은 적어서 소스마다 따로 잡습니다 |
| `MAX_ITEMS_PER_SITE` | 위 표에 없는 소스에 적용되는 기본 상한 (기본 15) |
| `REQUEST_TIMEOUT` | HTTP 타임아웃 초 (기본 15) |
| `SEND_DELAY_SECONDS` | 알림 전송 간 대기 초 (기본 1.5, rate limit 방지) |
| `BOOTSTRAP_ON_FIRST_RUN` | 첫 실행에서 알림 없이 기준점만 기록 (기본 True) |

상한은 **키워드 필터와 중복 제거를 모두 통과한 뒤** 적용됩니다. 즉 "1회 실행당 소스별 최대 신규 알림 건수"입니다. 이미 보낸 글은 상한 슬롯을 차지하지 않습니다.

상한에 걸려 제외된 항목이 생기면 WARNING이 찍힙니다. 제외된 항목은 `seen.json`에 기록되지 않아 다음 실행에서 재시도되지만, 매번 반복된다면 해당 소스의 신규 유입이 상한보다 많다는 뜻이니 `MAX_ITEMS_PER_SOURCE` 값을 올리세요.

```
[보안뉴스] 상한(20건)을 넘겨 7건을 이번 실행에서 제외했습니다. ...
```

## 주의사항

### boannews.py — EUC-KR

보안뉴스는 EUC-KR 인코딩입니다. `resp.apparent_encoding`은 잘못 감지될 수 있으므로 코드에서 `resp.encoding = "euc-kr"`를 명시합니다. 이 줄을 지우면 한글이 깨집니다. 검색어도 EUC-KR로 URL 인코딩해서 보냅니다.

### kisa_notice.py — 레거시 JSP 경로 폐기됨

원래 쓰던 `https://www.kisa.or.kr/notice/notice_List.jsp`는 **403을 반환합니다.** 헤더(Referer/User-Agent) 문제가 아니라 레거시 JSP 게시판 자체가 폐기된 것으로, 어떤 헤더 조합으로도 403입니다. 반면 사이트 루트는 평범한 User-Agent만으로 200이 옵니다.

현행 사이트는 숫자 경로를 씁니다. 실제 값으로 교체했고 별도 헤더는 필요 없습니다.

| | URL |
| --- | --- |
| 공지사항 목록 | `https://www.kisa.or.kr/401` |
| 상세 | `https://www.kisa.or.kr/401/form?postSeq={번호}` |

참고로 `/402` 보도자료, `/403` 입찰공고도 같은 구조라, 필요하면 `LIST_URL`만 바꿔 모듈을 복제하면 됩니다.

페이징 파라미터는 **`page`** 입니다 (`pageIndex`는 무시되고 항상 1페이지가 나오니 주의). `LIST_PAGES = 2`로 2페이지(20건)까지 읽습니다. 더 거슬러 올라가려면 이 값을 올리세요.

구조가 또 바뀌면 파일 상단에 모아둔 `LIST_URL` / `VIEW_URL` / `LIST_SELECTOR` / `TITLE_SELECTOR` / `DATE_SELECTOR` 상수만 수정하면 됩니다.

### thinkcontest.py — 내부 JSON API

```
POST https://www.thinkcontest.com/thinkgood/user/contest/subList.do
```

`searchKeyword` + `search_type=program_nm`으로 서버 측 검색이 되므로, `KEYWORDS`마다 한 번씩 검색해 `contest_pk`로 dedup합니다. 상세 URL은 `.../user/contest/view.do?contest_pk={pk}`입니다.

**함정**: 페이지는 `cryptoEncode.do`가 발급한 암호화 토큰을 `querystr`로 함께 보내지만, 이 값은 **아예 빼야** 합니다. 빈 문자열이라도 넣으면 서버가 빈 목록을 반환합니다. 키를 생략하면 인증 없이 정상 동작합니다. 또 응답은 `recordsPerPage`와 무관하게 요청당 10건으로 고정입니다.

### linkareer.py — 공개 GraphQL API

```
POST https://api.linkareer.com/graphql
```

`activities(filterBy, orderBy, pagination)` 쿼리를 인증 없이 호출합니다. `activityTypeID`는 **"3" = 공모전, "1" = 대외활동**입니다.

**제약**: 이 API의 `ActivityFilter`에는 키워드 검색 필드가 없습니다(introspection은 비활성화되어 있고 `keyword`/`search`/`query`/`title` 등은 모두 "not defined" 오류). 그래서 최신순 목록을 넉넉히(`PAGE_SIZE = 60`) 받아온 뒤 제목 키워드 필터에 맡깁니다. 보안 공모전이 링커리어에 올라오는 빈도가 낮아 이 소스는 대부분 0건입니다(실측: 최신 120건 중 0건). 놓치는 게 걱정되면 `PAGE_SIZE`를 올리세요.

스키마가 바뀌면 GraphQL 오류 메시지에 어떤 필드가 문제인지 그대로 나오므로, 로그의 경고 메시지를 보고 `QUERY` 상수를 고치면 됩니다.
