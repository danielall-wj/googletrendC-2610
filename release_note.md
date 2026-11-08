# Release Note — googletrendC-2610

## 2026-11-08

- 10/24~10/27 사이 수집이 멈춘 원인은 Actions 결제 실패(지출 한도 초과)로 job이 시작되지 않은 것이었습니다. 이후 해소됐습니다.
- 11/02부터 Explore 7d가 CI에서만 `ValueError`로 실패해 워크플로가 매번 실패로 표시되던 문제를 고쳤습니다. 로컬에서는 재현되지 않고, 국가별 첫 호출(7d)에서만 실패해 첫 호출 직후의 비정상 응답으로 보았습니다.
  - `scripts/explore.py`: 관련 검색어 호출(`related`)이 `ValueError`일 때 최대 3번까지 쉬었다가 다시 시도합니다.
  - 실패 로그에 예외 메시지(앞 120자)를 남겨, 다음에는 원인을 바로 알 수 있습니다.
- 확인: 수정 후 수동 실행이 성공했고 7d(KR·US·JP)가 모두 갱신됐습니다. 다만 이번에는 재시도 없이 첫 시도에서 성공해서, 11/02~11/08의 실패가 일시적인 구글 응답 문제였는지 재시도로 막을 수 있는 종류인지는 확정하지 못했습니다. 다시 실패하면 로그에 남는 예외 메시지로 원인을 확인합니다.

## 2026-10-27

- 저장소를 `frontierall` → `danielall-wj` 계정으로 이전하고 public으로 전환했습니다. 새 주소: https://github.com/danielall-wj/googletrendC-2610
- 이전 직전 Actions 실행이 실패하던 원인은 `frontierall` 계정의 Actions 사용 한도(spending limit) 초과였습니다. public 저장소는 Actions 사용 시간이 무료라 이전 후 해소됩니다.
- README의 GitHub·Actions 주소를 새 주소로 고쳤습니다.
- Vercel 프로젝트를 danielall-wj 쪽 Vercel(`frontierlim13-4143s-projects`)에 같은 이름 `googletrendc-2610`으로 새로 만들고 `danielall-wj/googletrendC-2610`에 연결했습니다. 옛 frontierall 프로젝트는 삭제했습니다. 사이트 주소(https://googletrendc-2610.vercel.app)는 그대로입니다.
