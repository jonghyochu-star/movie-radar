# Gemini v0.3 decision note — zero-new-API review

This note uses only already completed Gemini artifacts. No new Gemini request was used to make these decisions.

## Existing evidence reviewed

Full semantic reports were available for three completed analyses:

1. `csimNvZOXTs` — movie/drama expected
   - Gemini: yes / feature_film_scene / high
   - Relationship output included strangers, grandparent-grandchild, lovers
   - Emotional turn present at 02:11
   - Story completeness: partial
   - Aftertaste: strong
   - Story tags included reunion, romance, warm ending, longing

2. `VfVRkZBEDnc` — not movie/drama expected
   - Gemini: no / behind_the_scenes / high
   - Correctly recognized visible filming equipment, crew, stunt setup, and cut cue
   - Emotional turn: false
   - Story completeness: moment_only

3. `gSu2ghFxoiY` — movie/drama expected
   - Gemini: yes / feature_film_scene / high
   - Story arc: misunderstanding → truth → attitude change
   - Emotional turn at 00:27
   - Story completeness: complete
   - Tags included tension release, attitude reversal, catharsis

Earlier batch logs also showed four consecutive movie/drama classifications correct before quota/service interruption, but their full semantic reports were not preserved, so they are not used to judge story-analysis quality here.

## What is already good enough to keep

- Movie / non-movie structural classification
- Concrete visual/audio evidence
- Korean event summary
- Emotional-turn detection and timestamp
- Story-completeness signal
- Free-form story/emotional tags

These fields are useful and should remain in one video-analysis request.

## Problems found without spending another API call

### 1. Story arc taxonomy is too narrow

The reunion/first-love clip was forced into `기타` even though the event was understandable. A separate broader reusable story-pattern field is needed.

### 2. Relationship output is descriptive but noisy for learning

Multiple visible relationships can all be correct, but Movie Radar needs one primary emotional relationship for stable comparison across videos.

### 3. “Aftertaste” should not become a hidden quality score

Strong/medium/weak can help as evidence, but it must not directly mean “결 맞음”, “전개 약함”, or “제작 후보”.

### 4. Free-form story tags are useful but inconsistent

They are good for explanation and discovery, but synonym drift makes them weak as the only learning signal. Controlled relationship/story-pattern fields should sit beside them.

### 5. The next architecture decision is not simply “SRT or video”

Some scenes depend heavily on facial expression, action, visual reveal, or editing. Others are dialogue-led. The analyzer should describe visual dependency and whether transcript-only first-pass analysis is likely sufficient.

## v0.3 schema direction

Keep existing fields and add:

- `primary_relationship`
- `story_pattern`
- `emotional_payoff`
- `setup_clear`
- `payoff_clear`
- `context_required`
- `visual_dependency`
- `transcript_sufficiency`

The model must NOT directly decide:

- 결 맞음 / 결 아님
- 많이 본 소재
- 전개 약함
- 제작 후보

Those are user/profile decisions. Gemini should produce descriptive evidence that Movie Radar can later compare with the user's records.

## Why this maps better to the current Movie Radar labels

- 결 맞음 / 결 아님 → later comparison against primary relationship + story pattern + emotional payoff + tags
- 많이 본 소재 → compare a candidate against the user's previously seen/marked material; not a one-video AI judgment
- 전개 약함 → use setup/payoff/completeness as evidence, calibrated against the user's own weak-story labels
- 제작 후보 → strongest explicit user decision; AI should not invent it
- SRT-first routing → use visual_dependency + transcript_sufficiency rather than assuming all videos are equally suited to transcript analysis

## Next API use

Do not repeat basic movie/non-movie tests.

The next new Gemini call should happen only when we are ready to validate the new v0.3 output structure on a small number of videos. One or two deliberately chosen clips can be enough for schema sanity checking before any larger batch.
