# Gemini Lab v0.2 · 일괄 블라인드 검증

최대 10개의 공개 YouTube 영상을 한 번에 Gemini로 분석합니다.

- 사람 정답 라벨은 Gemini 프롬프트에 전달하지 않습니다.
- 모든 영상 분석이 끝난 뒤 영화/드라마 장면 판별 정확도를 계산합니다.
- 오탐(false positive), 놓친 영화(false negative), uncertain 수를 따로 집계합니다.
- 입력/출력/thinking 토큰과 유료 단가 환산 추정 비용을 합산합니다.
- 좋아요/별로 취향 라벨은 이 단계에서 사용하지 않습니다. 기존 별로는 이유가 섞여 있으므로 취향 음성 정답으로 간주하지 않습니다.

## 입력 형식

`youtube_urls`
- 최대 10개
- 쉼표 또는 줄바꿈으로 구분

`expected_labels`
- 선택 입력
- `movie_drama`, `not_movie_drama`, `unknown`
- URL과 동일한 순서/개수
- 입력하지 않으면 모두 unknown으로 분석만 수행

결과는 Actions Artifact의 `gemini-lab-batch.json` 및 `gemini-lab-batch.md`에 저장됩니다.
