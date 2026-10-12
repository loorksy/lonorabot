import asyncio


async def drain(tasks: list[asyncio.Task[None]], grace_seconds: float = 25) -> None:
    if not tasks:
        return
    _, pending = await asyncio.wait(tasks, timeout=grace_seconds)
    for task in pending:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
