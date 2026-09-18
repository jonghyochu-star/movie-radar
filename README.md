# Movie Radar · 1.3

개인용 영화·드라마 쇼츠 후보 탐색 앱의 **수집 경로 개선 업데이트**입니다.
참고 자료는 예시이지 취향의 상한선이 아닙니다. 기존 저장소·워크플로·API Secret을 그대로 사용합니다.

## 이번에 구현한 것

- `discovery.json`의 네 검색 경로를 매 실행에 함께 사용합니다: 참고 결 / 다른 감동 이야기 / 참고 작품 / 새 소재.
- 8개 언어, 총 96개 검색 프로필에서 실행마다 4개를 선택합니다. 이것은 검색 의도이지 개별 영상의 감동 판정이 아닙니다.
- 참고 결 이외에도 용서와 두 번째 기회, 존엄과 인정, 노력에 대한 인정, 따뜻한 유머를 탐색합니다. 특정 인물관계나 감동 키워드를 필수 통과 조건으로 추가하지 않습니다.
- 사용자가 제공한 YouTube 예시 4개의 **영상 ID**를 API로 조회해 공개 채널 ID를 확인하고, 최대 4개 출처 채널에서 업로드 목록을 조회합니다. 링크와 업로드 파일 9개의 1:1 대응은 가정하지 않습니다.
- 제공된 참고 영상 자체는 새 후보에서 제외합니다. 참고 채널이 크더라도 출처 확인은 하며, 거기서 나온 새 후보는 기존 화면의 구독자 상한을 그대로 적용받습니다.
- 제목·태그의 `#shorts`는 표기 단서일 뿐입니다. 사용자 확인과 별도로 보관합니다. 카드에서 `쇼츠 맞음 · 확인` / `일반 영상 제외` / `쇼츠 확인 취소`를 사용할 수 있습니다.
- 일반 영상 제외는 기존 좋아요·메모·제작 상태를 삭제하지 않고, 탐색·보관함·제작 후보에서 숨깁니다. 평가 기록에서 취소할 수 있습니다.
- 경로별 표시와 경로 섞기를 추가합니다. 섞기를 켜면 엄격한 전체 조회수순은 아닙니다.
- 목록이 크기 상한을 넘으면 탐색 경로와 채널 규모 구간을 나눠 보존합니다. 큰 채널이 높은 조회수로 모든 자리를 차지하지 않도록 하며, 수치를 조작하거나 사용자 필터를 완화하지 않습니다.

## 적용 순서 (기존 1.2.1 위에)

1. 앱에서 `내 기록 백업`을 눌러 개인 PC에 보관합니다. 백업 파일은 GitHub에 올리지 않습니다.
2. 이 압축의 `upload` 안에 있는 `scripts`, `site`, `tests`, `discovery.json`, `README.md`를 기존 저장소 최상위에 업로드합니다.
3. 기존 `.github`, `config.json`, `site/data/videos.json`은 삭제하지 않습니다. API Secret도 변경하지 않습니다.
4. `Commit directly to the main branch`로 커밋합니다.
5. `Actions → Movie Radar → Run workflow → Branch: main / mode: live`로 **새 실행**을 시작합니다. 이전 실행의 Re-run은 사용하지 않습니다.
6. build/deploy 성공 뒤 앱에서 Ctrl+Shift+R로 새 화면을 불러옵니다.
7. 처음에는 `발견 경로: 모든 경로 함께`, `쇼츠 여부: 미확인 포함 · 일반 영상 제외`를 사용합니다. 구독자·조회수·언어·길이는 기존 선택이 유지되므로 원하는 값인지 확인합니다.

## 설정과 사용량

- `config.json`의 검색 횟수·기간·결과 개수·최대 길이·지정 영상·지정 채널 설정을 유지합니다.
- `discovery.json`이 있고 enabled가 true이면 **검색어 선택**은 새 프로필에서 진행합니다. 기존 `config.json`의 queries는 fallback입니다. enabled=false로 바꾸고 새 live 실행을 하면 기존 검색어 경로로 돌아갑니다.
- 기본 검색은 4개 × 최근/전체 기간 = **최대 8회 search 요청**입니다. 재시도는 별도입니다.
- 기본 참고 출처 확인은 videos 1회, channels 조회 및 출처당 playlistItems 1회(최대 4개 채널)를 추가합니다. 영상 상세·구독자 통계 요청은 영상 수에 따라 배치 처리되므로 전체 API 요청 수가 8회라는 뜻은 아닙니다.
- 출처 채널에서는 기본 최신 50개 업로드만 검사합니다. 해당 채널 전체를 검색하거나 YouTube 전체를 빠짐없이 수집하는 기능이 아닙니다.
- API 오류 시 출력을 덮어쓰지 않습니다. 삭제된 참고 영상은 건너뛰고 경고하며, quota 오류를 새 키로 우회하지 않습니다.
- 새 API 키, OpenAI API, 별도 외부 유료 분석 서비스를 사용하지 않습니다. API 키는 기존 GitHub Secret에서 읽습니다.

## 반드시 구분할 것

- **검색 경로는 추천 이유의 출처 설명이지, 영상을 봤다는 뜻이 아닙니다.**
- 감동결·원작 제작국·한국 영화 여부·실제 Shorts 분류를 완전 자동으로 확정하지 않습니다.
- `videoDuration=short`는 4분 미만 검색 옵션이며 Shorts 전용 필터가 아닙니다. 최종 수집 길이는 기존 3분 이하 범위를 유지합니다.
- '내가 확인한 쇼츠만' 필터는 사용자 확인 기록이 없으면 0개입니다. 모르는 것을 확인된 것으로 처리하지 않습니다.
- `shorts`나 `#shorts`가 있는 모든 결과가 Shorts인 것은 아닙니다. 정사각형 영상도 Shorts일 수 있어 화면 비율을 임의로 단정하지 않습니다.
- 소규모 채널 필터는 현재 공개 구독자 수 기준이며 영상 게시 당시 수치가 아닙니다.
- 브라우저의 좋아요/별로는 현재 GitHub 수집 설정을 자동 변경하지 않습니다. 지속적인 자동 취향 학습은 아직 구현하지 않았습니다.
- 실제 추천 품질은 새 live 결과로 평가해야 합니다. 모의 데이터 테스트 성공이 실제 검색 정확도를 의미하지 않습니다.

## 공개 범위와 기록

이 저장소가 Public이면 코드, 탐색 검색어, 참고 YouTube 영상 ID 네 개, 배포된 공개 목록이 공개됩니다. 사용자 영상 파일이나 분석 보고서 전체는 포함하지 않습니다. API 키와 브라우저의 좋아요·메모는 업로드하지 않습니다.

기존 `movie-radar:v1:<앱 경로>:records`, `filters-v1.2` 저장 키를 유지합니다. 쇼츠 사용자 확인만 새 필드로 추가하고, 원작 판정·취향 평가·제작 상태와 분리합니다. API 캐시는 29일 갱신/삭제 방식과 사용자 데이터만 백업하는 기존 방식을 유지합니다. 다른 브라우저로 자동 동기화하지 않습니다.

## 로컬 테스트

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/test_core.cjs
```

82개 Python 테스트와 74개 JavaScript 테스트가 통과했습니다. 모의 DOM·API 응답·localStorage를 사용한 별도 Chromium 화면 테스트 14개도 통과했습니다. 실제 YouTube API 호출, 계정 Secret, GitHub 배포 및 실사용 후보 정확도는 여기서 시험하지 않았습니다. 상세 기록은 압축 최상위 TEST_REPORT.md에 있습니다.

공식 구현 근거:
- YouTube search.list: https://developers.google.com/youtube/v3/docs/search/list
- YouTube videos.list: https://developers.google.com/youtube/v3/docs/videos/list
- YouTube playlistItems.list: https://developers.google.com/youtube/v3/docs/playlistItems/list
- GitHub 수동 실행: https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow
