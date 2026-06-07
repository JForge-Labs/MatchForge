#!/usr/bin/env python3
"""Capacity gate unit tests."""
import asyncio

import pytest
from fastapi import HTTPException

from app.services import capacity_service


def test_capacity_detail_shape():
    detail = capacity_service.capacity_detail()
    assert detail["error"] == "capacity"
    assert "influx" in detail["message"].lower()
    assert detail["retry_after_seconds"] > 0


def test_raise_if_overloaded_when_kill_switch(monkeypatch):
    monkeypatch.setenv("OVERLOAD_MODE", "true")
    from app.core.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        capacity_service.raise_if_overloaded()
    assert exc.value.status_code == 503
    assert exc.value.detail["error"] == "capacity"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_heavy_work_slot_releases(monkeypatch):
    monkeypatch.setenv("OVERLOAD_MODE", "false")
    monkeypatch.setenv("CAPACITY_MAX_CONCURRENT_UPLOADS", "2")
    from app.core.config import get_settings

    get_settings.cache_clear()
    capacity_service._heavy_inflight = 0

    async with capacity_service.heavy_work_slot():
        assert capacity_service.heavy_slots_in_use() == 1
    assert capacity_service.heavy_slots_in_use() == 0
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_heavy_work_slot_rejects_when_saturated(monkeypatch):
    monkeypatch.setenv("OVERLOAD_MODE", "false")
    monkeypatch.setenv("CAPACITY_MAX_CONCURRENT_UPLOADS", "1")
    from app.core.config import get_settings

    get_settings.cache_clear()
    capacity_service._heavy_inflight = 1

    with pytest.raises(HTTPException) as exc:
        async with capacity_service.heavy_work_slot():
            pass
    assert exc.value.status_code == 503
    assert exc.value.detail["error"] == "capacity"
    capacity_service._heavy_inflight = 0
    get_settings.cache_clear()