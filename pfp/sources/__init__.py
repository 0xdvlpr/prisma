"""Collectors. Each takes a Country and a time window and returns a list of Story.

A collector must never raise for network or parsing problems: it logs and returns
what it has, so one failing source never blanks a country.
"""
from __future__ import annotations

import logging
from typing import Callable, Protocol

from ..countries import Country
from ..models import Story

log = logging.getLogger("pfp.sources")


class Collector(Protocol):
    name: str

    def collect(self, country: Country, hours: int) -> list[Story]: ...


def safe(fn: Callable[[], list[Story]], label: str) -> list[Story]:
    try:
        return fn() or []
    except Exception as exc:  # noqa: BLE001 - collectors must not take the run down
        log.warning("%s failed: %s", label, exc)
        return []
