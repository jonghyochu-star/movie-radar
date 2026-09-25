# Route Check v0.2 — HTTP 400 대응 기록

## 확인된 사실

- Route Check #2, run `36123089456`, commit `c26dc3dc5e80751c1d550a73589ceaefff38b337`.
- 보관된 artifact `gemini-route-check-2-1`의 실제 기록: `failed`, 요청 1회, HTTP 400, `INVALID_ARGUMENT`, 경과 0.179초.
- 분석/사용 토큰은 제공되지 않았습니다. 실패 요청의 실제 한도 차감이나 청구액을 추정하지 않습니다.
- v0.1은 오류 코드만 남겼습니다. Google 오류 원문의 구체적인 거부 항목은 복구할 수 없으므로 이 수정이 유일한 원인이라고 단정하지 않습니다.

## 공식 명세와 코드의 불일치

확인일: 2026-09-25.

공식 REST reference의 `GenerationConfig.responseFormat.text.mimeType`은 문자열 MIME이 아니라 `MimeType` enum이며 JSON 값은 `APPLICATION_JSON`입니다.
v0.1은 이 자리에 `application/json`을 사용했습니다. v0.2에서는 해당 값 하나만 `APPLICATION_JSON`으로 변경했습니다.

주의: HTTP `Content-Type` 헤더와 기존 `generationConfig.responseMimeType`은 별도 필드로, `application/json` 문자열을 사용합니다. 헤더는 변경하지 않았습니다.

공식 가이드의 일부 예제는 소문자 MIME 문자열을 표시하여 REST reference와 표현이 일치하지 않습니다. 본 수정은 정식 REST 필드 명세를 기준으로 했습니다. 공식 예제와도 대조했지만 실제 API 호환성이 보장됐다고 주장하지 않습니다.

참조:
- https://ai.google.dev/api/generate-content#textresponseformat
- https://ai.google.dev/api/generate-content#generationconfig
- https://ai.google.dev/gemini-api/docs/generate-content/structured-output

## 추가 보호 장치

- 요청 전 형식 검사: 이전 MIME 값이 다시 들어오면 요청 0회로 중단합니다.
- 허용목록 기반 `errorFields`, 고정 분류 `errorKind`를 추가했습니다.
- `google.rpc.BadRequest`의 필드명과 알려진 parser 위치만 추립니다. 오류 원문/입력값/임의 경로/API 키/모델 사고 출력은 저장하지 않습니다.
- 서버가 상세를 보내지 않거나 알려진 패턴에 맞지 않으면 세부 원인은 계속 미확인입니다.
- 진단 버전은 `0.2`이며 로그에 버전을 표시합니다.

## 유지한 것

동일 모델, 영상, PROMPT, v0.3 schema를 유지했습니다. 기존 Lab/Batch/워크플로/사이트/사용자 평가 데이터는 변경하지 않았습니다.
실행은 여전히 명시적 체크가 필요하고 최대 1회 요청만 보냅니다. 재시도, 자동 모델/경로 전환, 리다이렉트는 없습니다.

## 오프라인 검증 범위

Route Check 전용 검사 27개(기존 20개 + 추가 7개)가 로컬에서 통과했습니다. HTTP 진입점을 mock 처리했고 socket 연결도 차단했습니다. 실제 Gemini 요청은 0회입니다.
로컬 실행에는 저장소에서 읽은 공용 함수/PROMPT/schema 구간을 사용했습니다. PROMPT와 schema의 SHA-256은 실패 artifact에 기록된 값과 일치함을 확인했습니다. 전체 프로젝트 또는 실제 Google 서버 검증을 수행한 것은 아닙니다.
수정한 스크립트와 테스트의 업로드 blob SHA가 로컬에서 검사한 파일과 동일함도 확인했습니다. GitHub 다음 실행은 저장소의 전체 공용 모듈을 사용해 오프라인 검사를 먼저 수행합니다.

테스트의 400 상세 오류 예시는 합성 fixture이며 #2의 복구된 서버 원문이 아닙니다.

## 다음 실제 실행

Actions → Movie Radar Gemini Route Check → 새 Run workflow.
Branch `main`, 기존 영상 `gSu2ghFxoiY`, `confirm_live_call` 체크.
기존 실행의 Re-run jobs는 사용하지 않습니다. 수정 전 커밋으로 돌아가기 때문입니다.
한 번 실행한 후 결과부터 검토하고 자동/연속 재실행하지 않습니다.
성공해도 한 건의 호환성/분석 결과 확보일 뿐 안정성 전체 검증은 아닙니다.
