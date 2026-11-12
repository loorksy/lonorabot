# #119 (3cc0c6d9) and #192 (37f8b110) — R-DOOR: rebase request (main 0341d70d, batch 8)

- #119 conflicts in ar/en messages.po, manifest.json, lonora_agent/environment.py; #192 in the same plus apps/web/src/lib/user_error.ts. Merge main, regenerate catalogs and manifest, and keep 0086/0087 on main's migration head. I re-check the merge with --remerge-diff and rerun the migration and core checks.
