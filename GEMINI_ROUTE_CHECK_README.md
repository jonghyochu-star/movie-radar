# Gemini Route Check — 1회 요청 경로 진단

## 목적과 현재 상태

기존 Interactions Lab의 503 이후, 같은 모델·YouTube 영상·PROMPT·v0.3 schema를
`generateContent`로 요청할 수 있도록 분리한 진단 도구입니다.
기존 `gemini_lab.py`, Batch, 수집·평가·사이트 데이터는 변경하지 않습니다.
새 코드는 기존 Lab에서 모델·PROMPT·schema·URL 검증 함수를 직접 가져옵니다.

코드와 새 진단의 오프라인 검사 20개를 준비했습니다. 이 작업에서 Gemini 실제
요청은 하지 않았습니다. 실제 호환성 및 v0.3 이야기 분석 검증은 아직 필요합니다.
GitHub 실행에서도 해당 오프라인 검사를 먼저 수행합니다.

## 화면 해석

사용자가 제공한 비율 제한 화면은 기간이 28일이며 '최대 사용량'을 표시합니다.
`5/5`, `23/20`은 지금의 분당/일일 잔여량으로 단정할 수 없습니다.
차트 끝의 0 역시 현재 요청의 반영 여부나 남은 호출 횟수를 보장하지 않습니다.
직전 실행에 반환된 503은 서비스 오류이며, 그 자체로 한도 리셋 여부를 증명하지 않습니다.
실패 요청의 실제 할당량 차감/청구 여부는 이번 보고서로 추정하지 않습니다.

## 실행

Actions → **Movie Radar Gemini Route Check** → **Run workflow**

- Branch: `main`
- `youtube_url`: `https://www.youtube.com/watch?v=gSu2ghFxoiY`
- `confirm_live_call`: 체크하면 실제 요청을 최대 1회 전송합니다.
- 체크하지 않으면 기본값인 오프라인 준비만 합니다. 별도 API 리셋 확인 호출은 하지 않습니다.

로컬 실행도 `--live` 없이는 API를 호출하지 않습니다.

```bash
python scripts/gemini_route_check.py --youtube-url 'https://www.youtube.com/watch?v=gSu2ghFxoiY'
# 실제 호출에는 GEMINI_API_KEY 환경 변수와 명시적 --live가 모두 필요합니다.
```

이 진단에는 자동 재시도·자동 모델 전환·자동 요청 경로 전환이 없습니다.
HTTP 리다이렉트도 따라가지 않으며, 네트워크 타임아웃에도 재시도하지 않습니다.
같은 프로젝트의 한도를 우회하거나 새 무료 할당량을 만드는 기능이 아닙니다.

## 결과

Artifacts의 `gemini-route-check-<실행번호>-<시도번호>`에서 JSON과 Markdown을 확인합니다.
HTTP/API 오류에도 진단 파일을 만들며, 업로드 단계는 `if: always()`입니다.
오프라인 검사 자체가 실패하거나 작업이 강제 종료되면 보고서가 없을 수 있습니다.

- `prepared`: 실제 요청 0회. 요청 준비만 확인했으며 API 성공이 아닙니다.
- `success`: 완료 응답에서 v0.3 항목의 형식 검사를 통과했습니다. 내용의 정확성은 별도 검토합니다.
- `failed`: 오류/차단/불완전한 JSON/분석 schema 불일치 등. 자동 재실행하지 않습니다.

오류 원문, API 키, 원본 모델 사고 출력은 보고서에 저장하지 않습니다.
HTTP 상태·허용목록의 오류 코드·숫자형 Retry-After·소요 시간만 기록합니다.
반환된 토큰 수는 항목별로 보존하고, 미제공 값은 0이 아닌 미확인으로 남깁니다.
경로 간 토큰 계산을 임의로 합산하거나 실패 비용을 $0으로 표시하지 않습니다.

## 결과에 따른 다음 판단

성공하면 새 v0.3 이야기 분석을 검토하고 기존 결과와 비교합니다.
단 한 번의 성공은 안정성 검증이 아니며, 이전 Interactions 실패와 실행 시점이
다르므로 '기존 경로가 장애 원인'이라고 확정할 수 없습니다.
다시 503이면 이 변경만으로 해결되지 않은 것으로 기록하고 반복 호출을 멈춥니다.
429면 현재 한도 상세를 확인하고, 400이면 요청 호환성을 먼저 코드/문서로 재검토합니다.
추가 실험은 그 결과가 설계 결정을 바꾸는 경우에만 정합니다.

## 공식 근거 (2026-09-25 확인)

- Interactions 권장 및 generateContent 지원 유지:
  https://ai.google.dev/gemini-api/docs/interactions-overview
- Gemini 3.8 Flash + YouTube URL의 generateContent 예제:
  https://ai.google.dev/gemini-api/docs/generate-content/video-understanding
- generateContent 구조화 출력 및 `generationConfig.responseFormat.text`:
  https://ai.google.dev/gemini-api/docs/generate-content/structured-output
- Interactions의 429/503 오류 코드:
  https://ai.google.dev/gemini-api/docs/api-errors

YouTube URL 입력은 Preview입니다. 두 경로가 내부 영상 처리 서비스를 공유할
가능성은 배제할 수 없으며, 어느 경로도 이번 변경만으로 안정성을 보장하지 않습니다.
