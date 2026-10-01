# 지금, 트렌드

Google Trends의 실제 데이터를 수집하는 정적 대시보드입니다. 한국·미국·일본의 실시간 인기 검색어, 관련 뉴스, Explore 상위·급상승 검색어, 수집 히스토리를 제공합니다.

구현 기준은 [사용자가 지정한 계획서](docs/implementation-plan.html)입니다. 원본 프로젝트는 수정하지 않았고 이 `googletrend-c-2610` 폴더에 구현했습니다.

## 실행

Node.js 22 이상과 Python 3.12 이상을 사용합니다. Node 패키지 설치나 프런트엔드 빌드는 필요 없습니다.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm start
```

브라우저에서 http://localhost:3000 을 엽니다. 실제 수집한 JSON이 `public/data/`에 포함되어 있습니다. HTML 파일을 `file://`로 직접 열면 브라우저의 fetch 제한 때문에 데이터를 읽을 수 없습니다.

새 데이터 수집:

```sh
.venv/bin/python scripts/fetch_trends.py --geo KR,US,JP --hours 4,24,48,168
.venv/bin/python scripts/explore.py --geo KR,US,JP --periods 7d,1m,3m,12m --once-per-day
```

## 기능

- 실시간: 4·12·24·48시간·7일, 국가 선택, 카테고리, 검색, 검색량·증가율·최신순, 상승 중 필터.
- 12시간: **수집 시점** 기준 최근 12시간 안에 시작한 항목을 24시간 원본에서 필터링합니다. 검색량·증가율은 24시간 원본 값입니다.
- 상세: 관련 검색어, 상태·시작/종료 시각, 뉴스 최대 3건, 원문 링크, 최근 수집 이력. 키워드 상세는 `#open=검색어`로 공유할 수 있습니다.
- 뉴스: Google Trends RSS 연결 기사를 우선 사용하고 Google 뉴스 키워드 검색 결과로 보강합니다. 후자는 Google Trends가 직접 연결한 기사와 다르므로 화면에 출처 유형을 표시합니다. 본문을 복제하지 않습니다.
- Explore: 지난 1주·1개월·3개월·1년, Top/Rising 전환, 상대 점수·성장률·급등, 직전 기간 순위 비교. 전체 카테고리·웹 검색만 수집합니다.
- 순위 비교: 현재 구간 직전의 같은 길이 **달력 일자 구간**을 별도 조회합니다. Google 새 화면의 변화율이 아닙니다. 비교 구간은 JSON/CSV에 보존합니다. 상대 시간 조회와 일자 조회의 경계는 근사 비교입니다.
- NEW: 실시간 화면은 직전 정상 스냅샷 대비 새 검색어입니다. 첫 수집은 NEW를 붙이지 않습니다. Explore NEW는 직전 기간의 상위 목록에 없던 항목입니다.
- 히스토리: 국가·날짜별 JSONL과 시점 슬라이더. 90일 지난 파일은 월별 gzip으로 압축하고 브라우저에서 읽습니다. 과거 기록에는 뉴스·관련 검색어를 넣지 않습니다.
- CSV/JSON: 현재 필터에 맞는 **전체** 결과. UTF-8 BOM, CSV 수식 방지, 국가·기간·수집 시각 포함.
- 다크 모드·모바일 화면·5분 자동 최신 파일 확인. 숨겨진 탭과 과거 기록 조회 중에는 자동 갱신하지 않습니다.

## 확정된 예약 시간

| 작업 | 일정 | GitHub cron (UTC) |
|---|---|---|
| 실시간 트렌드 + 뉴스 | **2시간마다** | `7 */2 * * *` |
| Explore | 수집 워크플로에서 하루 첫 성공 때 1회 | 날짜별 중복 수집 방지 |
| CSV 자동 보관 | **18:00 KST** | `0 9 * * *` |
| 한국·일본·미국 Discord | **19:00 KST · 하루 1회** | `0 10 * * *` |

GitHub Actions 스케줄은 지연되거나 누락될 수 있으므로 정확한 시각 보장은 없습니다. 실시간 데이터가 3시간, Explore가 36시간 넘게 오래되면 화면에 알립니다.

## 매일 18시 CSV 자동 보관

`archive.yml`은 최신 2시간 수집본을 `archives/csv/YYYY-MM-DD/`에 국가·기간별 CSV로 저장하고 커밋합니다. 한국·미국·일본의 4·24·48시간·7일 목록 및 이용 가능한 Explore 4개 기간을 보관합니다. 12시간은 파생 화면이므로 원본 24시간 CSV로 보존합니다. 해당 시점에 새로 Google을 조회하는 작업은 아닙니다.

파일마다 원본 수집 시각을 포함하고 `manifest.json`에 보관 시각·파일 목록·생략된 Explore를 기록합니다. 실시간 수집본이 3시간 넘게 오래되거나 누락되면 당일 폴더를 만들지 않고 실패합니다. Explore는 36시간 이내 데이터만 포함합니다. 같은 날짜 재실행 시 기존 보관본을 덮어쓰지 않습니다. CSV는 비공개 저장소에 보관하며 Vercel 배포에서 제외됩니다. 화면의 수동 CSV 다운로드는 계속 사용할 수 있습니다.

```sh
.venv/bin/python scripts/archive_csv.py
```

## Discord

발행 제목은 **구글 트렌드 코덱스**이며 분할 메시지마다 표시합니다.

매일 19시 한국 시간에 **한국·일본·미국 각각 최근 24시간 검색량 TOP 5**와 **검색어별 관련 뉴스 최대 3건**을 보냅니다. 총 15개 검색어·최대 45개 기사입니다. 3건 미만이면 실제 확보된 개수를 표시합니다. 국가별 카드가 Discord 글자 수 제한을 넘으면 여러 메시지로 분할하며, CSV/JSON 첨부는 각 국가 첫 메시지에만 포함합니다. 이번 발송 구성은 TOP 5·뉴스 중심이며 별도 Explore 요약 카드는 보내지 않습니다.

🆕는 직전 성공한 일일 브리핑의 해당 국가 전체 목록에 없던 현재 검색어입니다. 이전 기준선이 없으면 표시하지 않습니다. 전송 중 각 메시지 진행 상태를 기록하고, 결과가 불확실한 전송은 자동 재시도하지 않습니다. 이때 채널을 확인한 뒤 상태 파일을 검토해야 합니다.

참고 프로젝트 `YT-Daily-Brief-2608`처럼 색상별 embed 카드와 CSV/JSON 첨부로 발송합니다. 사용자/역할 멘션은 비활성화합니다. 발송 이력과 일일 기준선은 공개 웹 폴더 밖의 `state/discord.json`에 기록합니다.

```sh
cp .env.example .env.local  # 최초 설정 시에만; 이미 설정된 파일을 덮어쓰지 마세요.
# .env.local에 DISCORD_WEBHOOK_URL과 선택적 DASHBOARD_URL 설정
.venv/bin/python scripts/notify_discord.py --slot daily --dry-run
.venv/bin/python scripts/notify_discord.py --slot test
```

이 작업 중 제공된 웹훅은 권한 600인 `.env.local`에 설정했습니다. git과 Vercel 업로드에서 제외하며 로그에 출력하지 않습니다. `.env.local`은 로컬에서만 사용합니다. Actions에는 별도 Secret 등록이 필요합니다.

같은 날짜·슬롯은 한 번 성공하면 재발송하지 않습니다. 429는 제한적으로 재시도하며, 전송 결과가 불확실한 연결 타임아웃은 중복 메시지를 피하려고 자동 재전송하지 않습니다. 웹훅 API와 git 커밋을 하나의 원자적 트랜잭션으로 만들 수는 없으므로, 전송 직후 러너가 종료되거나 상태 push가 실패하면 수동 재실행 전에 채널을 확인해야 합니다.

## GitHub / Vercel 연결

**로컬 구현과 실제 데이터 수집·Discord 테스트 발송은 완료했습니다. 아직 이 폴더에 원격 저장소가 연결되지 않아 예약 실행·Vercel 공개 배포는 활성화되지 않았습니다.** 로컬 서버를 켜는 것만으로 수집·발송 예약이 실행되지는 않습니다.

1. 개인 계정 소유의 비공개 GitHub 저장소를 만들고 이 폴더를 올립니다. `.env.local`과 `.venv`는 포함하지 않습니다.
2. 저장소 Settings → Secrets and variables → Actions에 다음을 설정합니다.

| 종류 | 이름 | 값 |
|---|---|---|
| Secret | `DISCORD_WEBHOOK_URL` | 사용자가 지정한 Discord 웹훅 |
| Variable | `COMMIT_NAME` | Vercel 소유자와 연결된 GitHub 커밋 이름 |
| Variable | `COMMIT_EMAIL` | 해당 GitHub 계정에 연결된 이메일 또는 noreply 이메일 |
| Variable | `DASHBOARD_URL` | 배포 후 사이트 주소. 비어 있으면 Google 원문 연결 |

3. Vercel에서 저장소를 Import합니다. Framework: **Other**, Output directory: **public**, Build command: 없음. `vercel.json`에 설정되어 있습니다.
4. Actions의 **Collect Google Trends**를 수동 실행해 데이터 커밋과 Vercel 배포를 확인합니다. 이어 **Discord briefing**에서 `test`를 실행합니다.
5. 워크플로가 기본 브랜치에 올라가면 정해진 cron으로 수집/발송합니다. 비공개 저장소의 Actions 한도와 Vercel 플랜 조건은 계정에서 확인하세요.

Vercel Hobby의 비공개 저장소 Git 배포는 커밋 작성자가 프로젝트 소유자와 연결되어 있어야 합니다. 관련 문서: [Vercel Git 배포](https://vercel.com/docs/git), [GitHub 예약 실행](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). 수집 workflow는 데이터 push 뒤 별도 GitHub push workflow 실행에 의존하지 않습니다. Vercel의 Git 연동이 배포합니다.

코드는 비공개 저장소에 두더라도 **배포된 사이트와 `public/data/`는 공개**됩니다. 웹훅과 발송 기록은 배포 대상에 포함되지 않습니다.

## 안정성과 한계

- 비공식 Google 엔드포인트를 사용합니다. 사이트 구조 변경·지역별 차이·429·IP 제한이 생길 수 있습니다. 파싱 실패 시 기존 정상 JSON을 덮어쓰지 않습니다.
- 실시간 목록은 batchexecute `i0OFE`를 기본으로, 페이지 내 JSON을 보조로 읽습니다. RSS 10개를 전체 목록인 것처럼 대체하지 않습니다.
- 뉴스는 6시간 캐시, 국가별 새 검색 요청 최대 80개, 국가별 시간 예산 120초, 연속 실패 시 중단합니다. 인기 키워드부터 조회하므로 일부 검색어는 기사가 없을 수 있고 이후 수집에서 보강됩니다. 첫 실제 수집은 국가당 35회로 검증했습니다.
- 한 국가/기간이 실패해도 성공한 다른 결과는 저장합니다. index의 오류 메타데이터를 화면에 보여줍니다. 수집 workflow가 연속 실패하면 중복 없이 GitHub 이슈를 생성합니다.
- Explore 현재 데이터는 성공하고 비교만 실패하면 현재 데이터는 저장하되 순위 변화는 ‘비교 없음’으로 표시합니다.
- 검색량 구간값을 기간끼리 합산하지 않습니다. 상대 점수나 급등 sentinel을 실제 검색량으로 표시하지 않습니다.
- JSONL의 90일 이후 압축은 작업 트리 용량을 줄입니다. 과거 git 커밋 자체는 줄지 않으므로 저장소가 커지면 객체 스토리지 이전 등을 검토해야 합니다.
- 수집 히스토리는 가동 이후의 기록입니다. Explore 1년 결과는 Google에서 직접 조회하므로 1년을 기다릴 필요는 없습니다.

## 검증

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
node --check public/app.js
# Chrome이 설치된 환경에서, npm start 실행 후:
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python tests/browser_check.py
```

파서·날짜 경계·첫 수집 기준선·히스토리 압축·뉴스 필드·CSV·Discord 메시지 제한 및 3개국 TOP 5·뉴스 3건·분할 발송·일일 중복 방지·CSV 일별 보관를 검증합니다. 브라우저 검증은 실제 로컬 데이터를 사용하며 `test-results/`에 화면과 내보내기 파일을 저장합니다.

데이터 경로: `/data/index.json`, `/data/latest/KR/24.json`, `/data/explore/KR/1m.json`, `/data/history/KR/YYYY-MM-DD.jsonl`.
