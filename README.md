# Movie Radar · Starter 1.1

개인용 영화 쇼츠 소재 검토 앱. 기존 movie-radar 저장소에 적용하는 업데이트입니다.

## 현재 구현한 범위

- 영어 고정 검색을 해제했습니다. 영어·스페인어·포르투갈어·일본어·프랑스어·독일어·힌디어·인도네시아어·러시아어·태국어·아랍어·튀르키예어·중국어(간체/번체)·이탈리아어·베트남어 검색 프로필 16개를 사용합니다.
- 실행 번호에 따라 매회 프로필 4개를 선택합니다. 각 검색어로 최근 30일과 전체 기간을 검색하므로, 재시도를 제외한 검색 요청은 회당 최대 8번입니다. 영상/채널 정보 조회는 별도입니다. 실행 횟수나 quota를 우회하는 키 순환은 없습니다.
- regionCode를 고정해 보내지 않습니다. 언어 우선 설정은 특정 국가/언어의 영상만 검색한다는 보장이 아닙니다.
- 결과는 조회수와 구독자 수 등의 공개 수치를 비교하는 후보 목록입니다. 자동 영화/감동결/Shorts 인식이나 취향 학습은 아직 없습니다.
- 원작 제작국은 YouTube API 정보만으로 추정하지 않습니다. 모든 새로운 실제 영상은 원작 확인 필요로 분리합니다.
- 사용자가 원작을 확인한 뒤 '한국 외 원작 확인'을 누르면 소재 탐색에서 검토할 수 있습니다. 미확인 상태에서도 좋아요와 메모는 저장할 수 있지만, 제작 후보 지정 전에는 원작을 확인해야 합니다.
- '한국 영화 제외'는 사용자가 확인한 **해당 YouTube 영상 ID**에 적용됩니다. 추천·좋아요 목록·제작 후보에서 숨기고 평가 기록에는 남깁니다. 동일 영화의 다른 재편집 영상/다른 ID를 자동으로 찾아 제외하지 않습니다.
- 원작 확인 취소 및 분류 변경이 가능합니다. 원작 분류는 취향의 좋아요/별로와 독립적으로 저장합니다.

## 사용자 기록

기존 localStorage 키(movie-radar:v1:경로:records)와 schema 1을 유지합니다. 기존 좋아요·제작 상태·메모는 삭제하지 않습니다. 실제 영상의 이전 기록에 원작 정보가 없으면 unknown으로 취급합니다. 원작 정보가 없는 기존 제작 후보는 상태를 보존하되 원작 확인 전에는 후보 화면에서 숨깁니다. 샘플 후보는 종전처럼 표시합니다.

브라우저 기록은 자동 동기화되지 않습니다. 업데이트 전 하단 '내 기록 백업'으로 별도 백업하세요. 백업은 영상 ID와 사용자 기록만 포함하고 API 제목·조회수·썸네일 캐시는 포함하지 않습니다. 사용자 원작 분류도 함께 백업합니다.

## 설치 상태와 실행

1. 기존 저장소의 API 키 Secret 이름은 YOUTUBE_API_KEY 그대로 유지합니다.
2. 패키지 upload 안의 site, scripts, tests, config.json, README.md를 기존 저장소 최상위에 업로드하고 main에 커밋합니다. 동일 경로의 앱 코드만 교체합니다.
3. .github/workflows/movie-radar.yml과 site/data/videos.json은 이 업데이트에 포함하지 않으며 삭제하지 않습니다. 저장소나 API 키를 새로 만들 필요가 없습니다.
4. 커밋 이후 기존 수동 워크플로 Actions → Movie Radar → Run workflow에서 main / live로 실행해야 새 코드와 실제 목록이 배포됩니다. 저장만으로 배포가 자동 실행되는 구성은 아닙니다.
5. 배포 후 브라우저에서 Ctrl+Shift+R로 최신 화면을 불러옵니다. 첫 실제 수집 영상은 원작 확인 필요 탭에 있습니다.
6. API 연결·배포 성공을 확인하기 전에는 AUTO_COLLECT를 켜지 않습니다.

## 실제로 확인하지 않은 항목

개발 환경에는 사용자의 API 키가 없으므로 실제 YouTube 요청과 사용자 GitHub 배포는 테스트하지 않았습니다. 라이브 검색 품질과 호출 한도, 원작 제작국은 실제 실행/검토가 필요합니다.

## 개발 테스트

python -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/test_core.cjs

첨부 TEST_REPORT.md에 이번 검증 범위를 기록했습니다. 기존 워크플로는 Python 테스트를 실행하며 Node 테스트는 이번 개발 검증 환경에서 별도로 실행했습니다.

## 보안·이용

API 키는 Actions의 Secret에만 넣습니다. 설정 파일/소스/사용자 메모에 키를 넣지 않습니다. 영상 파일은 다운로드하지 않습니다. 공개 API 정보는 갱신 시점 기준이며, 앱에서는 오래된 캐시 표시를 제한합니다. 원작 이용권한/재사용 콘텐츠 정책은 별도로 확인하세요.

## 참고 문서

- YouTube search.list: https://developers.google.com/youtube/v3/docs/search/list
- YouTube video resource: https://developers.google.com/youtube/v3/docs/videos
- GitHub Secrets: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
