# Gap 2: what Lonora does with files and images the owner sends

Repository HEAD 9f5b1da (the checked-out tree is 0a03960, two docs-only commits later; `git diff --stat 9f5b1da HEAD -- apps packages` is empty, so the code is identical). All runs on database 8 with an isolated, uniquely named agent per run. Driver: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/gap2_vision.py` (argument V1..V7). Raw output: `/tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/runs/gap2-V*.txt`.

## 0. Scope and honesty about the evidence

- In the production conversation the owner never sent a file or image. The only images are ones Lonora sent him (`lonora-chat.md:163-170`, in the audit scratchpad, not the repo; `[صورة مرفقة]` after «ارسل صورة الشارات»). So this gap is a LATENT cause of the "I can't read it" class, not an observed production failure. It would fire the first time he sends a chart screenshot, a PDF or a phone photo.
- REAL in every run: the API app, the real multipart route `POST /api/artifacts/upload`, real message admission, PostgreSQL, the context builder, the tool loop, the `artifact_read` tool, the run executor. SCRIPTED: only which tool calls the "model" makes, and its final text (always labelled). No provider was called, so nothing here shows what a real vision model would say. The evidence is what the runtime put into the model request and what a tool returned.
- The isolated test agent is not the production Personal Agent. In the test agent `artifact_read` is a native tool (V1 tool list). In production the 23 native tools do NOT include `artifact_read` (`TIMELINE_CORRECTION.md:21`, audit scratchpad), so there the model would first have to find it through `tool_environment` / `tool_call`. UNSURE: I did not run the Personal Agent's exact tool exposure for this file path.

## 1. The attachment path, read from the code

| Step | What the code does | Citation |
|---|---|---|
| Web upload | the chat composer uploads with `thread_id` only, never `agent_id`; limit 6 files, 8 MB each | `apps/web/src/lib/api.ts:131-136`, `apps/web/src/conversation/Composer.tsx:61`, `:282` |
| Mobile upload | also `thread_id` only | `apps/mobile/lib/api.ts:182` |
| Stored type | whatever the browser claimed; empty or `application/octet-stream` becomes `text/plain` only for a text suffix, otherwise stays `application/octet-stream` | `apps/api/src/lonora_api/routes/artifacts.py:22-26` |
| No content check at upload | bytes written and hashed, nothing validated | `apps/api/src/lonora_api/routes/artifacts.py:35-56` |
| Admission | a missing or foreign artifact id is rejected with `artifact_not_found` before the run exists | `packages/db/src/lonora_db/messages.py:381-383` |
| Context | `attachment_parts` reads only the focus message (`focus = submission_seq or run.input_seq`) | `packages/agent-runtime/src/lonora_agent/context/builder.py:148-153`, `attachments.py:28-34` |
| Note line | every attachment adds `"Artifact " + id + ": " + name` | `packages/agent-runtime/src/lonora_agent/context/attachments.py:41` |
| Image rule | only `image/png`, `image/jpeg`, `image/webp`, `image/gif`, size at most 5 MiB, no decode check | `attachments.py:44-51` |
| Text rule | `text/*` or `application/json`, cut to 24,000 characters, no marker | `attachments.py:52-53` |
| Anything else | falls through both branches: no pixels, no text, no note beyond the id and name | `attachments.py:41-53` |
| Foreign artifact skip | `continue`; unreachable in normal use because admission already rejects it | `attachments.py:37-38`, `messages.py:381-383` |
| Where the pixels go | onto the newest owner message in the request, as `target.images` | `builder.py:278-283` |
| Routing | any message with images forces `Capability.VISION`; the agent's own model is used unless the catalog verified it as text-only | `packages/agent-runtime/src/lonora_agent/model_runtime.py:99-100`, `packages/providers/src/lonora_providers/router.py:90-97` |
| Mid-run send | steering path builds the same note plus pixels | `packages/agent-runtime/src/lonora_agent/steering.py:26-39` |
| Reading later | `artifact_read` with `view_image=true` calls `load_image_observation` (`artifacts.py:214-215`), which raises `artifacts_not_found` unless `row.agent_id == context.agent_id` AND the same thread. Plain `read` (no `view_image`) only applies that check to internal tool-result artifacts (`artifacts.py:206-208`), so metadata/text reads of owner uploads work (V2) | `packages/tools/src/lonora_tools/artifacts.py:139`; tool text at `:249`, exposure `:253` |

`image_observations.py` (the file named in the assignment) is only the TOOL-result image path: it matches `artifact_read` calls with `view_image` true (`packages/agent-runtime/src/lonora_agent/context/image_observations.py:24-29`), re-reads the file through `load_image_observation` (`:79-81`), and caps at 4 images and 20 MiB (`:13-14`). It never sees owner attachments. `tests/check_image_observations.py` and `tests/test_image_observations.py` only cover images the agent made itself (`chart_snapshot`).

Test coverage: no Python test exercises `attachment_parts` against a real upload. The two matches in `tests/test_context_engine.py:299` and `tests/test_skill_runtime.py:314` replace it with a mock. (`grep -rn "attachment_parts" tests`.)

### Existing checks run

```
cd /home/user/lonorabot && source /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/env.sh 8 && (cd tests && ../.venv/bin/python check_image_observations.py)
PASS real chart_snapshot -> artifact_read -> same Run VISION pixels; complete multi-tool block; reference-only checkpoint/restart; scope, hash, missing/MIME/dimension/size rejection
.venv/bin/python -m pytest tests/test_image_observations.py -q   ->   12 passed
```

They pass because the agent's own chart image is stored with the agent's id and thread. The same tool refuses an image the owner uploaded through the chat (V1 below). Output: `runs/gap2-check_image_observations.txt`, `runs/gap2-test_image_observations.txt`.

## 2. Journeys

Rerun prefix for all: `cd /home/user/lonorabot && source /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/env.sh 8 && .venv/bin/python /tmp/claude-0/-home-user-lonorabot/a10b53f8-e308-561e-ac54-852bd1cce6ca/scratchpad/audit/scripts/gap2_vision.py V<n>`

### V1. Chart screenshot plus «حلل هذا»: pixels arrive, but the follow-up read tool dead-ends with a code

- Owner request: PNG 800x600 chart screenshot attached, text «حلل هذا». Uploaded exactly as the web composer does (thread id, no agent id).
- Real upload row: `"agent_id": null, "thread_id": "<thread>"`, `"media_type": "image/png"`.
- Model request 1 (REAL, built by the runtime): capability `vision`; the owner message `"حلل هذا"` carries `1 image(s)` (`data:image/png;base64,iVBORw0KGgoAAAANSU...`, 7686 chars); a context section `<context_section name="attachments" source="owner_attachments" trust="owner_supplied_untrusted" priority="92">Artifact c104d836-fba7-4e41-9f88-9039b3c9b231: gold-chart.png</context_section>`. So the first look works.
- SCRIPTED turn: the model calls `artifact_read {"artifact_id": "<id>", "view_image": true}` (a plausible move, because the context shows only an "Artifact <id>" line and the tool description says "Set view_image=true to inspect an owned raster image", `artifacts.py:249`).
- Literal runtime tool result:
  `{"ok": false, "code": "artifacts_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", "safe_to_retry": false, "schema_tool": "tool_environment", "attempt": 1, "retry_exhausted": false}}`
- What the owner sees: nothing from the runtime; any "I can't open the image" text would be the model's own wording from this result. The file exists, is owned and is on this very thread. The error is false.
- Root cause: `load_image_observation` rejects when `row.agent_id != context.agent_id` (`packages/tools/src/lonora_tools/artifacts.py:139`); chat uploads are stored with `agent_id = null` (`apps/api/src/lonora_api/routes/artifacts.py:58-59`, client sends only `thread_id`, `apps/web/src/lib/api.ts:134`). The code `artifacts_not_found` is the generic "not found" and hides the real reason. The recovery block names `tool_environment` and says not to retry, which leads nowhere.
- Class: BUG (plus a leaked internal code, `artifacts_not_found`, in the model's view; recovery pointer is a dead end).
- Run output: `runs/gap2-V1.txt`.

### V2. PDF plus «لخّص لي هذا الملف»: the model gets a name and an id, no content, no tool to read it

- Owner request: `broker-statement.pdf` (`application/pdf`), «لخّص لي هذا الملف».
- Model request 1 (REAL): capability `conversation` (no image, so no vision), no image, the only trace of the file is `Artifact 87e7c7ea-f1b3-486e-89f4-b85da927276c: broker-statement.pdf`.
- SCRIPTED turn: `artifact_read {"artifact_id": "<id>"}`.
- Literal runtime result (trimmed): `{"ok": true, "id": "87e7...", "agent_id": null, "thread_id": "...", "payload": {"name": "broker-statement.pdf", "key": "87e7.../broker-statement.pdf", "size": 193, "media_type": "application/pdf", "sha256": "794a..."}, "state": {}, "version": 1, ...}` with no `content` field. Success, but empty of substance. It also hands the model the storage `key` and `sha256`, which are internal.
- Registry check: no tool name contains `pdf` (`runs/gap2-V2.txt`, last block: `[]`).
- What the owner sees: whatever the real model says given this; the likely honest answer is "I can't read PDFs". The runtime offers no safe next step.
- Root cause: `attachments.py:44-53` handles only four raster types and text; `read` returns text only for `text/*` and JSON (`packages/tools/src/lonora_tools/artifacts.py:221`), and `view_image` only for rasters (`:142-143`). No extraction exists for PDF, spreadsheets or Office files.
- Class: DEAD-END (no tool exists; the only way out is the owner pasting the text). Raw metadata including storage key is a minor LEAK.
- Run output: `runs/gap2-V2.txt`.

### V3. Large phone screenshot (6.7 MB PNG) plus «حلل هذا»: image silently dropped

- Owner request: a 1500x1500 PNG of 6,761,059 bytes, text «حلل هذا». The web composer allows up to 8 MB (`apps/web/src/conversation/Composer.tsx:61`) and the backend upload allows 20 MiB (`packages/core/src/lonora_core/attachments.py:5`), so the upload succeeds.
- Model request 1 (REAL): capability `conversation`, `any image anywhere? false`, and the only mention of the file is `Artifact a88d9d85-df41-4f95-bc26-8d379d50c74d: screenshot.png`.
- What the owner sees: no notice from the runtime in the code path (no branch reports the drop); the web toast at `Composer.tsx:276` only fires for files over 8 MB. UNSURE: I did not drive a browser, so I could not see whether the web UI shows anything else after send.
- Root cause: `path.stat().st_size <= 5 * 1024 * 1024` (`attachments.py:47`); if false the code falls to the `elif`, which is also false (`attachments.py:52`), and the loop moves on silently. The 5 MiB model limit and the 8 MB composer limit disagree for exactly the files phones produce.
- Class: BUG (silent drop; the model believes there is an image it cannot see, and may then say it cannot read it or ask the owner to resend, both from a recoverable cause: a resize would fix it).
- Run output: `runs/gap2-V3.txt`.

### V4. Matrix: what the real `attachment_parts` gives the model for 14 kinds of file

Each file was uploaded through the real route, attached to a real message, and the real function was called. "images" = pixels sent to the model.

| File (stored media type) | images | text/notes the model gets |
|---|---|---|
| chart.png (image/png) | 1 valid | id and name |
| photo.jpg (image/jpeg) | 1 valid | id and name |
| photo-nonstd.jpg (`image/jpg`) | 0 | id and name only |
| phone.heic (`image/heic`) | 0 | id and name only |
| logo.svg (`image/svg+xml`) | 0 | id and name only |
| untyped.png (browser sent no type, stored `application/octet-stream`) | 0 | id and name only |
| fake.png (bytes "this is not an image", `image/png`) | 1, NOT a valid image (`UnidentifiedImageError`) | id and name |
| report.pdf | 0 | id and name only |
| sheet.xlsx | 0 | id and name only |
| notes.txt | 0 | id, name and the text («ملاحظات: الدخول 4050») |
| data.csv, data.json, page.html | 0 | id, name and the content |
| big.txt (30,000 chars) | 0 | 24,055 characters (24,000 of content plus header), no truncation marker |

- Root cause: the exact-match set at `attachments.py:46` (`image/jpg` is not in it); the type is whatever the client claimed (`routes/artifacts.py:24-26`); no decode happens before pixels are sent (`attachments.py:49-51`), unlike the tool path, which decodes and checks format and dimensions (`packages/tools/src/lonora_tools/artifacts.py:112-127`); the text cut has no marker (`attachments.py:53`).
- Class per row: `image/jpg`, untyped `.png`, oversize: BUG (recoverable by sniffing the real type or resizing). `.heic`, `.svg`, `.pdf`, `.xlsx`: DEAD-END (no reader; the owner must convert). `fake.png`: BUG; UNSURE what a real provider returns for an undecodable image, I did not call one, but the runtime forwards it unchecked. 24,000 cut: BUG (minor, the model is not told the text is partial).
- Run output: `runs/gap2-V4.txt`.

### V5. Follow-up turn loses the image: «حلل هذا» then «وين أحط الستوب؟»

- Owner requests: turn 1 screenshot plus «حلل هذا»; turn 2, a new message with no attachment, «وين أحط الستوب؟».
- Turn 1 model request (REAL): capability `vision`, 1 image, the attachments section (as V1).
- Turn 2 model request (REAL): capability `conversation`; `any image in the model request? false`; no attachments section. History the model sees: user `"حلل هذا"`, assistant `"SCRIPTED turn-1 reply: analysis of the chart."` (my scripted text, not evidence), user `"وين أحط الستوب؟"`. Nothing marks that the first message had a file, and the file id is not in context, so the model cannot even call `artifact_read` on it.
- What the owner sees: whatever the model makes of a question about a chart it can no longer see; the likely forms are "send the chart again" (a technical-looking request for something already sent) or an answer from its own earlier text.
- Root cause: `attachment_parts` reads only the focus message's attachments (`attachments.py:28-35`, called with `focus` at `builder.py:148-153`) and pixels attach only to the newest owner message (`builder.py:278-283`). Nothing re-attaches earlier files, and the history rendering carries no attachment marker (no use of `attachment_ids` anywhere in `packages/agent-runtime/src` except `attachments.py` and `steering.py`; `grep -rn attachment_ids`).
- Class: BUG (owner-visible context loss; recoverable by keeping the note and offering a re-read, but the re-read tool itself fails per V1).
- Run output: `runs/gap2-V5.txt`.

### V6. `view_image` on a PDF: the same false error, hiding the real reason

- SCRIPTED turn: `artifact_read {"artifact_id": "<pdf id>", "view_image": true}`.
- Literal result: `{"ok": false, "code": "artifacts_not_found", "recovery": {"category": "not_found", "next_action": "inspect_existing_state", "safe_to_retry": false, "schema_tool": "tool_environment", ...}}`.
- Root cause: the agent-id check at `packages/tools/src/lonora_tools/artifacts.py:139` fires before the media-type check at `:141-143`, which would have said `artifact_image_format_unsupported`. So even the accurate reason is masked.
- Class: BUG (leak of an internal code that names the wrong cause).
- Run output: `runs/gap2-V6.txt`.

### V7. Screenshot sent while a run is already working (steering path): works

- Two messages: «شو وضع الذهب؟», then, while the run was leased, the screenshot plus «حلل هذا». `merge_steering` returned true and the run state received the user message `"حلل هذا\n\n<untrusted_attachments>\nArtifact de857de6-...: gold-chart.png\n</untrusted_attachments>"` with 1 image.
- Finding: the mid-run path does attach the pixels (`steering.py:26-39`). It shares the same limits as V3/V4 because it reuses `attachment_parts`. No separate failure found.
- Class: no failure (control case). Run output: `runs/gap2-V7.txt`.

## 3. Failure outcomes and per-family counts

| Family | Outcomes | Count | Classes |
|---|---|---|---|
| ATT-1 read-back tool refuses owner's own file (`artifacts_not_found`) | V1, V6 | 2 | BUG, LEAK |
| ATT-2 no reader exists for non-image, non-text files | PDF, xlsx, heic, svg | 4 | DEAD-END |
| ATT-3 silent drop of a supported-looking image | over 5 MiB, `image/jpg`, untyped `.png` | 3 | BUG |
| ATT-4 undecoded bytes forwarded as pixels | fake.png | 1 | BUG (provider result UNSURE) |
| ATT-5 attachment gone on later turns | V5 | 1 | BUG |
| ATT-6 text cut without a marker | big.txt | 1 | BUG (minor) |
| Total | | 12 | BUG 8 (one UNSURE), DEAD-END 4, plus 2 of the BUGs also leak a code or storage key |

None of these is "needed for safety". The upload and read scope rules (owner id, thread id) are sound; the agent-id equality at `artifacts.py:139` is wrong for chat uploads rather than a safety feature, because chat uploads are owner-owned and thread-scoped. This is a judgement; the repository has no comment explaining why `agent_id` is required there.

## 4. Doc versus code

- `packages/tools/src/lonora_tools/artifacts.py:249` says "Set view_image=true to inspect an owned raster image in the next model turn". "Owned" is true for the owner's upload but the code at `:139` also demands the agent's id, so it fails for chat uploads. Code wins; the description over-promises.
- `docs/research/lonora-runtime-notes/map-tools-world.md:132` describes `artifact_read` as metadata plus a 24,000-char text page and `view_image` handing a raster to the next turn; it does not mention that owner uploads are excluded.

## 4b. Added by checker

- The tool-path image limits are the same 5 MiB (`packages/tools/src/lonora_tools/artifacts.py:103`) plus a 4096x4096 cap (`:117`), so fixing the agent-id check alone would still refuse a large phone screenshot via `view_image` (`artifact_image_too_large` at `:148`, `artifact_image_dimensions_exceeded` at `:118`).
- Absence claim re-checked with two methods: no tool in `packages/tools/src` whose registered name contains pdf/file/doc/sheet/ocr (only `workspace_read`, `artifact_read`, `*_read` market tools), and no PDF/Office/OCR library in any `pyproject.toml` (`grep -niE "pypdf|pdfplumber|fitz|openpyxl|tesseract"` empty). `workspace_read` reads only the agent's own workspace and says "binary files require artifact handling" (`packages/tools/src/lonora_tools/workspace.py:100`); no workspace tool takes an owner-uploaded `artifact_id` (grep for `ArtifactRow|artifact_id` in `workspace.py` and `workspace_artifacts.py` is empty), so it is no recovery path for V2.

## 5. What I could not confirm

- What a real provider returns for a `image/png` with invalid bytes (V4 fake.png).
- Whether the production model (`openai/gpt-5.4-mini`, `production-trace.md:80`, audit scratchpad) is verified vision-capable in the catalog; the router sends images unless the catalog verifies the model as text-only (`router.py:96-97`).
- What the web UI shows the owner after a dropped image; I did not drive a browser.
- Whether the Personal Agent would find `artifact_read` through `tool_environment` at all (V1 and V2 used an agent where it is native).

## Verification log

- Citations opened: about 54 explicit `file:line` tokens plus bare `:NNN` and range follow-ups (every repo citation plus the three audit-scratchpad notes), all re-read against the source at tree 0a03960 (code identical to 9f5b1da).
- Citations corrected: 0 line numbers. Fixes were presentation: the "Foreign artifact skip" row had its citation in the wrong table column; the three scratchpad-file citations (`lonora-chat.md`, `TIMELINE_CORRECTION.md`, `production-trace.md`) are now labelled as audit files, not repo files; the HEAD statement now notes the tree is 2 docs-only commits ahead.
- Quotes checked: tool text `artifacts.py:249`, all runtime result strings, Arabic strings (`حلل هذا`, `لخّص لي هذا الملف`, `وين أحط الستوب؟`, `ملاحظات: الدخول 4050`), `image_observations.py:24-29`: all match.
- Journeys V1-V7 rerun with the given prefix on database 8: outputs identical to `runs/gap2-V*.txt` apart from agent names, ids and timestamps. V1/V6 `artifacts_not_found`, V2 no `content` field, V3 no image, V4 matrix, all reproduced.
- Counts recomputed: 14 files in V4; family table 2+4+3+1+1+1 = 12; BUG 8, DEAD-END 4. Correct.
- Claims refuted or downgraded: none refuted. The "no PDF reader" and "no attachment marker in history" absence claims survived a second grep method each.
- Added: section 4b (tool-path 5 MiB/4096 limits remain after any agent-id fix; `workspace_read` is not a recovery path; plain `read` of owner uploads does work); `read` vs `view_image` distinction in the "Reading later" row.
- Caveat kept: V1/V2/V6 use a test agent where `artifact_read` is native, so the Personal Agent exposure remains UNSURE (already stated in section 0).
