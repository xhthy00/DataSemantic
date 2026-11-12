import asyncio
import json
import sys
import time

from .errors import ServiceError
from .registry import Bundle


class Planner:
    def __init__(self, concurrency: int, queue_timeout: float = 0.0):
        self.slots: asyncio.Queue[None] = asyncio.Queue(concurrency)
        for _ in range(concurrency):
            self.slots.put_nowait(None)
        # Bounded wait for a free slot: parallel callers queue instead of
        # failing immediately; only exhaustion of this budget returns 503.
        self.queue_timeout = max(0.0, queue_timeout)
        self.processes: set[asyncio.subprocess.Process] = set()
        self.closed = False

    async def _acquire(self, code: str, message: str) -> None:
        if self.closed:
            raise ServiceError("SERVICE_STOPPING", "Service is stopping", 503)
        if self.queue_timeout <= 0:
            try:
                self.slots.get_nowait()
            except asyncio.QueueEmpty:
                raise ServiceError(code, message, 503) from None
            return
        try:
            await asyncio.wait_for(self.slots.get(), self.queue_timeout)
        except TimeoutError:
            raise ServiceError(code, message, 503) from None

    async def _stop(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        await process.wait()

    async def close(self) -> None:
        self.closed = True
        await asyncio.gather(*(self._stop(proc) for proc in tuple(self.processes)))

    async def run(
        self, bundle: Bundle, sql: str | None, timeout: float, *, diagnostics: bool = False
    ) -> tuple[dict, int]:
        await self._acquire("PLANNER_BUSY", "All planning slots are occupied; retry later")
        process = None
        started = time.monotonic()
        try:
            async with asyncio.timeout(timeout):
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "wren_semantic.worker",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                self.processes.add(process)
                payload = {
                    "operation": "validate" if sql is None else "plan",
                    "manifest": bundle.encoded_manifest,
                    "dialect": bundle.entry.dialect,
                    "names": bundle.queryable_names,
                    "sql": sql,
                    "diagnostics": diagnostics,
                }
                stdout, _ = await process.communicate(json.dumps(payload).encode())
            if process.returncode != 0:
                raise ServiceError("WORKER_FAILED", "Planning worker exited unexpectedly", 500)
            try:
                result = json.loads(stdout)
                if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
                    raise ValueError("Invalid worker response")
            except (ValueError, UnicodeError):
                raise ServiceError(
                    "WORKER_FAILED", "Invalid planning worker response", 500
                ) from None
            if not result["ok"]:
                code = result.get("code", "WORKER_FAILED")
                raise ServiceError(
                    code,
                    result.get("message", "Planning failed"),
                    500 if code == "WORKER_FAILED" else 422,
                    result.get("sdk_code"),
                )
            return result, round((time.monotonic() - started) * 1000)
        except TimeoutError:
            raise ServiceError("PLANNING_TIMEOUT", "Planning deadline exceeded", 504) from None
        finally:
            if process is not None:
                # A timeout/cancellation must kill and reap native work, not just abandon it.
                await asyncio.shield(self._stop(process))
                self.processes.discard(process)
            self.slots.put_nowait(None)
