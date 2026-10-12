import asyncio


async def drain(tasks: list[asyncio.Task[None]], timeout: float = 25) -> None:
    if not tasks:
        return
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    for task in pending:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
