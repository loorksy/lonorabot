#!/usr/bin/env python3
"""Review or explicitly apply proven historical image attachments. Dry-run is the default."""

import argparse
import asyncio
import hashlib
import json
from typing import Any
from uuid import UUID

from lonora_api.env import get_settings
from lonora_core.user_error import LonoraError
from lonora_db.artifact_repair import repair_completed_images
from lonora_db.client import Database
from lonora_db.schema import RunRow, ThreadRow
from lonora_security.runtime_storage import confined_path
from sqlalchemy import select


async def repair(owner_id: str, limit: int, apply: bool) -> dict[str, Any]:
    settings = get_settings()
    db = Database.connect(settings.database_url)
    reports: list[dict[str, Any]] = []
    try:
        async with db.sessions() as session:
            run_ids = list(
                await session.scalars(
                    select(RunRow.id)
                    .join(ThreadRow, ThreadRow.id == RunRow.thread_id)
                    .where(
                        ThreadRow.owner_id == owner_id,
                        RunRow.status == "completed",
                        RunRow.model_metadata["result_message_id"].as_string().is_not(None),
                    )
                    .order_by(RunRow.created_at.desc())
                    .limit(limit)
                )
            )
        for run_id in run_ids:
            async with db.sessions() as session:
                plan = await repair_completed_images(session, owner_id, run_id)
            if not plan["candidates"]:
                continue
            verified: set[str] = set()
            unavailable: list[str] = []
            for candidate in plan["candidates"]:
                try:
                    path = confined_path(settings.artifact_root, candidate["key"])
                    if (
                        path.is_file()
                        and hashlib.sha256(path.read_bytes()).hexdigest() == candidate["sha256"]
                    ):
                        verified.add(candidate["artifact_id"])
                    else:
                        unavailable.append(candidate["artifact_id"])
                except (OSError, ValueError, LonoraError):
                    unavailable.append(candidate["artifact_id"])
            if apply and verified:
                async with db.sessions() as session, session.begin():
                    plan = await repair_completed_images(
                        session, owner_id, run_id, apply=True, verified_artifact_ids=verified
                    )
            reports.append(
                {
                    "run_id": run_id,
                    "message_id": plan["message_id"],
                    "eligible": sorted(verified),
                    "unavailable_or_hash_mismatch": unavailable,
                    "applied": plan["applied"],
                }
            )
        return {
            "mode": "apply" if apply else "dry-run",
            "scanned_runs": len(run_ids),
            "limit": limit,
            "messages": reports,
        }
    finally:
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", required=True, type=lambda value: str(UUID(value)))
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply only recorded, owner-scoped, hash-verified image attachments.",
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")
    print(json.dumps(asyncio.run(repair(args.owner, args.limit, args.apply)), ensure_ascii=False))
