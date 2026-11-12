# PR #136 at fcdd8b11 (W-MOBILE 3: composer uploads)

- PR: #136, `mobile/3-attachments`
- Head: fcdd8b11
- Stacked on `mobile/2-message-actions` ab84ede6 (#118, itself on #95). Reviewed: its own commits 60256b9a and 09e269db; the merge fcdd8b11 only brings in #118.
- Diff: `ab84ede6..fcdd8b11`, 20 files, mobile only.
- Verdict: **FINDINGS** (0 high, 0 medium, 3 low)

## Verified findings

### L1 (low): when a sent message's upload fails, the owner's typed text is lost
- **What happens:** the text leaves the draft at send (`consumeComposerDraft`). On a failed upload the row becomes «لم تُرسل» with Delete only:
  - `components/message-menu.tsx:96-99` hides Retry;
  - `thread.tsx` `retryOutgoing` returns on `uploading?.length`.
- There is no Copy on that sheet. Uploaded siblings stay orphaned on the server.
- **Parity:** this is exactly what #76's web does (`apps/web/src/lib/outgoing-messages.ts` `settleOutgoingUploads`; `Conversation.tsx:521-530`: "Files that never arrived cannot be sent again: only «حذف» is left"). It is a faithful port of a gap the two clients share, so low. I raised the web side with W-UI too.
- **Fix (both clients):** on settle failure, return the text, reply and finished attachments to the draft (as `handBack` does) and drop the row. Or offer Copy, or "send without the files", on the failed sheet.

### L2 (low): `handBack` restores an upload that has already failed, as a ring that never ends
- **Where:** `apps/mobile/lib/composer-uploads.ts:93-101`. `running = back.filter((row) => !row.result)` does not check whether `done` rejected. `pick`'s catch returns silently while `upload.sent`.
- **Reproduced** with a throwaway node test (startUpload → handOver → reject transfer → handBack): one stale row stays.
- A later send hands the dead row over again and fails. The window is narrow: an upload failure between handOver and an enqueue failure such as `outbox_full`.
- **Fix:** set a `failed` flag in the rejection handler and filter it out in `handBack`.

### L3 (low): the specs never check which artifact was posted (14.1.3)
- **Where:** `tests/mobile/composer-uploads.spec.mjs:112,143` assert only `attachment_ids` `toHaveLength(1)`. Test 1 cancels b.txt but never asserts the posted id is a.txt's.
- **Fix:** record the ids the mocked upload returns, and assert `posted[0].attachment_ids` equals the non-cancelled one.

## Rejected candidates
- **"'As on Web' is untrue: web has no ring, no cancel and no send while uploading (0.4)":** main's web blocks send while uploading (`Composer.tsx:296`). But the conversation surface W-MOBILE ports is #76's web, which has all three: `UploadRing.tsx` with `role="progressbar"` and «Cancel the upload» (ar present), and `canSend = … || uploads.length` (`Composer.tsx:386`). The lead's #76 review explicitly keeps the "upload ring". If #76 does not land first, the comments become untrue at that commit; land #76 first.
- **"Over 10 attachments via a handOver/enqueue-failure race":** traced in code only, not reproduced. The server refuses more than 10 ids anyway (`domain.py:117`).

## What I checked
- **Endpoints and limits:** the same `POST /api/artifacts/upload` (multipart `file`, `thread_id`), with ids in `body.attachment_ids`. The server enforces 20 MB, `safe_filename`/`confined_path`, owner check per attachment id (`artifact_not_found`) and at most 10 ids.
- **Failed or cancelled uploads:** a failed upload never posts. A cancelled upload is never attached. A server or session change rejects an in-flight upload.
- **Offline queue:** a row still uploading persists as `sending`, hydrates as `failed` and is never flushed. Once settled, it takes web's `isPlainOutgoing`/`flushQueued` path.
- **Privacy:** no uri or path is persisted or shown; only the name, size and media type.
- **Arabic and RTL:** all 7 new labels have Arabic. Rows use `row-reverse`.
- **P5, Stop, section 6:** P5 holds (the picker is an in-conversation sheet). Stop is untouched. Section 6 is not touched.
- **Tests at the head:**
  - `tsx --test tests/mobile/*.test.ts`: 80/80.
  - `pnpm --filter @lonora/mobile check`: exit 0.
  - Playwright `composer-uploads`: 4/4. `message-actions`: 5/5.
  - `workspace.spec.mjs` fails at the «إرسال» `toBeEnabled` step. It also fails on the base #118 and on main (pre-existing).
