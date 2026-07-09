"""Unit tests for ItemList identifier coercion."""

from __future__ import annotations

import queue
import threading
import time

import pytest
from unittest.mock import MagicMock


def test_itemlist_accepts_unhashable_attribute_dict_identifiers():
    from jsonapi_client.resourceobject import AttributeDict

    from adapters.persistence.models import ItemList

    class RawList(ItemList):
        def __init__(self, sources):
            self.identifier = lambda e: e
            super().__init__(sources)

    poster = AttributeDict(
        {"small": "http://example/s", "medium": "http://example/m"},
        resource=MagicMock(),
    )
    items = RawList(iter([poster]))

    deadline = time.time() + 2.0
    while time.time() < deadline and not items.list:
        time.sleep(0.01)

    assert len(items.list) == 1


def test_coerce_hashable_identifier_prefers_nested_id():
    from adapters.persistence.models import _coerce_hashable_identifier

    coerced = _coerce_hashable_identifier({"id": 42, "url": "http://example"})
    assert coerced == 42
