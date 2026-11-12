# PR #88 — W-BROKER 1 re-review at 0cffae1b

- Head: 0cffae1b; new commit since 4a827334: 0cffae1 ("R-SEC fixes")
- Reviewer: R-SEC
- Verdict: **FINDINGS** (0 high / 0 medium / 1 low, carried over)
- Conflicts with main e27c2357: none

## Status of the earlier findings
- M1 (a retried create made a second account): **fixed.**
  - `_post_create` sends the SDK's create request with a stable `transaction-id` derived from the caller's `request_key` (sha256, 32 lowercase letters).
  - My earlier probe, re-run: two attempts now carry the same id (`jcdjnelncdmffdmfhhniofhlhknnmfac` ×2).
  - New test `test_a_create_sent_again_carries_the_same_transaction_id`.
- M2 (a created account reported as a refusal): **fixed.** Refusals are read only from the create's own answer. A failed follow-up read after an id was returned now looks the account up (probe: no longer `broker_rate_limited`), and the `REFUSALS` comment is now true.
- L2 (docstring describing a caller): **fixed.** It now reads "Callers must hold …".
- L3 (no websocket assertion in the real-SDK test): **fixed.** It asserts `_socket_instances` is empty.
- L1 (low, still open): `metaapi_provisioning.py:142-146`. The SDK turns `httpx.ReadTimeout` into `ApiException(None, None, url)`, so a lost answer still maps to `broker_provisioning_unavailable`, never `broker_provisioning_timeout` (probe output unchanged). Safe, because `find` runs either way. Fix: map an `ApiException` whose `status_code is None` to the timeout code, or drop the dead branch.

## What I checked
- The new private SDK reach-in (`_metatrader_account_client._http_client.request`) still sends only to the SDK host through `validate_sdk_url`, with the token in `auth-token`. A non-JWT token is refused first.
- `scripts/agent_eval/broker.py` was updated for `request_key`.
- tests/test_metaapi_provisioning.py: 16 passed. ruff is clean.
