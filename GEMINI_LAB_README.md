# Movie Radar · Gemini Lab v0.1

본체 Movie Radar와 분리된 **1개 영상 블라인드 실험 모듈**입니다.

## 목적

1. 공개 YouTube URL을 Gemini가 실제로 읽을 수 있는지 확인
2. 영상이 실제 영화/드라마/단편/애니메이션 장면인지 먼저 판별
3. 장면이면 관계·사건 흐름·감정 전환·여운을 구조화해 추출
4. 사용자가 입력한 정답은 **모델 프롬프트에 전달하지 않고**, 결과가 나온 뒤에만 비교
5. 실제 토큰 사용량과 대략적인 유료 단가 비용을 보고서에 기록

## 안전 설계

- `GEMINI_API_KEY`는 GitHub Actions Secret에서만 읽습니다.
- 키를 URL, 로그, artifact, 공개 Pages에 쓰지 않습니다.
- Gemini Lab 결과는 GitHub Pages에 배포하지 않고 **Actions artifact**로만 14일 보관합니다.
- Movie Radar의 `site/data/videos.json`, 좋아요/별로 기록, Pages 배포를 수정하지 않습니다.

## 실행

GitHub → Actions → **Movie Radar Gemini Lab** → Run workflow

- `youtube_url`: 공개 YouTube 영상 URL
- `expected_label`: 사람이 이미 아는 정답
  - `unknown`: 정답 비교 안 함
  - `movie_drama`: 실제 각본 영화/드라마 계열 장면
  - `not_movie_drama`: 리뷰/BTS/인터뷰/튜토리얼/실사 사연/제품/게임 등

처음에는 **영상 1개만** 돌립니다.

## 출력

실행 완료 후 `Artifacts`의 `gemini-lab-report-*`를 내려받으면:

- `gemini-lab-report.json`
- `gemini-lab-report.md`

두 파일이 있습니다.

## 모델

기본 모델은 `gemini-3.8-flash`입니다.

## 비용 표시

보고서의 비용은 2026년 9~12월 공개 유료 단가를 이용한 **대략적인 비교용 계산**입니다. 실제 청구액과 다를 수 있습니다. 현재 Google 문서상 공개 YouTube URL 입력 기능은 Preview이며 no-charge로 안내되지만, 정책과 한도는 바뀔 수 있으므로 실제 토큰 사용량도 함께 기록합니다.
