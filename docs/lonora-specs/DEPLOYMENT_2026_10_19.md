# Production deployment — 2026-10-19

## Shipped revision

`0109438571a0460f827a5fd2c1773a8450b39d63` was pushed to `main` and deployed to `https://lonora.lork.cloud` using the existing production Compose services. The API and Gateway run the same newly built image. No APK was built. No database migration beyond the existing `0027_device_authority` head was required.

This release includes the previously verified chart command/creation receipts, server TradingView image capture, same-Run image observation, bounded conversation recall, retained Skill authority checks and exact-version owner revocations. It does **not** complete the broader Agent environment program or progressive Skill discovery/view.

## Checks actually executed

- Before release: 347 Python tests, 37 isolated PostgreSQL foundation groups and 11 Task cases passed; Ruff and strict Pyright passed.
- Before service replacement: the packaged image produced actual 1280×720 Chromium/TradingView PNGs for exact symbols `EURUSDm`, `XAUUSDm`, `US500.cash` and `BTCUSD#`, with four timeframes and Arabic/English rendering. The offline fixture used synthetic candles and no broker mutation.
- After replacement: public `/health` and `/ready` passed, including a fresh Gateway heartbeat. The dedicated chart renderer and its licensed library were served successfully.
- The current Android download still returned APK ZIP bytes. This verifies delivery, not a new native build or physical-device acceptance.
- Initial MetaApi history/stream subscription failures were observed during startup. Subsequent read-only checks fetched 500 candles through each of the three saved connections; all six saved charts recovered to `ready`. Market snapshots subsequently showed current candle and quote updates. This is observed recovery, not proof that every upstream failure is eliminated. No broker mutation was sent.

## Branch audit

All remaining fetched remote feature branches are ancestors of this release. The old local `feat/trading-goals-live-call` branch has a different commit history, but its complete tree equals `9d9d17c`, already present in `main`. No unique source change was omitted and no old branch was merged over newer source. No branch was deleted during this audit.

## Explicit no-backup deployment

At the owner's request, no new database, configuration or source backup was created. After service verification and the owner's explicit authorization, the old Lonora backup directory, old Compose backup, old source patch, duplicate untracked source snapshot and old APK `.bak` were deleted. The duplicate source file was compared byte-for-byte before deletion.

Current configuration, source, APK, OTA releases, database and artifact volumes were preserved. Named backup-file scans of the source, downloads and releases found none afterward. No unrelated VPS application, volume or system-wide Docker cache was pruned.

The reusable deployment script now supports explicit `--no-backup`; its default backup behavior remains unchanged for other deployments. The VPS uses its existing customized Compose configuration rather than the repository's alternative public-port stack.
