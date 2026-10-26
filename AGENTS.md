# Repository workflow

- Base new work on the latest `main`.
- Make subsequent implementation changes on a focused branch and submit a pull request into `main`.
- Do not push implementation changes directly to `main` unless the user explicitly authorizes that exception.
- Preserve unrelated work. Inspect all unique commits before removing a branch; delete merged branches after their pull request is merged.
- Keep credentials, local runtime files and generated build outputs out of commits.
- Run checks appropriate to the change, including `bash scripts/build.sh` when the user or release scope requires it.
