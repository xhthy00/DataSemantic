import asyncio
import sys
import time
from pathlib import Path

import pytest

from wren_semantic.errors import ServiceError
from wren_semantic.planner import Planner
from wren_semantic.registry import Registry

ROOT = Path(__file__).resolve().parents[1]


def test_timeout_kills_worker_and_releases_slot(monkeypatch):
    async def scenario():
        original = asyncio.create_subprocess_exec
        children = []

        async def sleeper(*args, **kwargs):
            child = await original(sys.executable, "-c", "import time; time.sleep(60)", **kwargs)
            children.append(child)
            return child

        monkeypatch.setattr(asyncio, "create_subprocess_exec", sleeper)
        planner = Planner(1)
        bundle = Registry(ROOT / "models/registry.json", 4_194_304).get("education-demo-v1")
        with pytest.raises(ServiceError) as caught:
            await planner.run(bundle, "SELECT 1", 0.2)
        assert caught.value.code == "PLANNING_TIMEOUT"
        assert children[0].returncode is not None
        assert not planner.processes and planner.slots.qsize() == 1
        monkeypatch.setattr(asyncio, "create_subprocess_exec", original)
        result, _ = await planner.run(bundle, "SELECT score_id FROM student_subject_score", 15)
        assert result["ok"]
        await planner.close()

    asyncio.run(scenario())


def test_busy_rejection_and_cancellation_reap_worker(monkeypatch):
    async def scenario():
        original = asyncio.create_subprocess_exec
        started = asyncio.Event()
        children = []

        async def sleeper(*args, **kwargs):
            child = await original(sys.executable, "-c", "import time; time.sleep(60)", **kwargs)
            children.append(child)
            started.set()
            return child

        monkeypatch.setattr(asyncio, "create_subprocess_exec", sleeper)
        planner = Planner(1)
        bundle = Registry(ROOT / "models/registry.json", 4_194_304).get("education-demo-v1")
        running = asyncio.create_task(planner.run(bundle, "SELECT 1", 30))
        await asyncio.wait_for(started.wait(), 5)
        with pytest.raises(ServiceError) as caught:
            await planner.run(bundle, "SELECT 1", 1)
        assert caught.value.code == "PLANNER_BUSY"
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert children[0].returncode is not None
        assert not planner.processes and planner.slots.qsize() == 1
        await planner.close()

    asyncio.run(scenario())


def test_planner_waits_for_slot_instead_of_rejecting():
    async def scenario():
        planner = Planner(1, queue_timeout=5)
        bundle = Registry(ROOT / "models/registry.json", 4_194_304).get("education-demo-v1")
        planner.slots.get_nowait()  # simulate a plan already holding the only slot
        queued = asyncio.create_task(
            planner.run(bundle, "SELECT score_id FROM student_subject_score", 15)
        )
        await asyncio.sleep(0.05)
        assert not queued.done()  # queued, not rejected
        planner.slots.put_nowait(None)
        result, _ = await queued
        assert result["ok"]
        assert planner.slots.qsize() == 1
        await planner.close()

    asyncio.run(scenario())


def test_planner_busy_only_after_queue_timeout():
    async def scenario():
        planner = Planner(1, queue_timeout=0.2)
        bundle = Registry(ROOT / "models/registry.json", 4_194_304).get("education-demo-v1")
        planner.slots.get_nowait()
        started = time.monotonic()
        with pytest.raises(ServiceError) as caught:
            await planner.run(bundle, "SELECT 1", 15)
        assert caught.value.code == "PLANNER_BUSY"
        assert time.monotonic() - started >= 0.2
        planner.slots.put_nowait(None)
        await planner.close()

    asyncio.run(scenario())
