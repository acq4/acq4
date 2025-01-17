from __future__ import annotations

from typing import Tuple, Any, Iterator, Set
from collections.abc import MutableMapping, MutableSet


class ApproxDict(MutableMapping):
    """A dictionary-like class that treats tuples of floats as approximately equal within a tolerance."""

    def __init__(self, tolerance: float = 1e-12):
        self.tolerance = tolerance
        self._data = {}  # Internal storage

    def _is_approx_equal(self, tuple1: Tuple[float, ...], tuple2: Tuple[float, ...]) -> bool:
        """Compare two tuples for approximate equality."""
        if len(tuple1) != len(tuple2):
            return False
        return all(abs(x - y) <= self.tolerance for x, y in zip(tuple1, tuple2))

    def _find_key(self, key: Tuple[float, ...]) -> Tuple[float, ...]:
        """Find an existing key that approximately matches the given key."""
        for existing_key in self._data:
            if self._is_approx_equal(existing_key, key):
                return existing_key
        return key

    def __getitem__(self, key: Tuple[float, ...]) -> Any:
        existing_key = self._find_key(key)
        try:
            return self._data[existing_key]
        except KeyError as e:
            raise KeyError(key) from e

    def __setitem__(self, key: Tuple[float, ...], value: Any) -> None:
        existing_key = self._find_key(key)
        self._data[existing_key] = value

    def __delitem__(self, key: Tuple[float, ...]) -> None:
        existing_key = self._find_key(key)
        try:
            del self._data[existing_key]
        except KeyError as e:
            raise KeyError(key) from e

    def __iter__(self) -> Iterator[Tuple[float, ...]]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"ApproxDict({dict(self)}, tolerance={self.tolerance})"


class ApproxSet(MutableSet):
    """A set-like class that treats tuples of floats as approximately equal within a tolerance."""

    def __init__(self, iterable=None, tolerance: float = 1e-12):
        self.tolerance = tolerance
        self._data: Set[Tuple[float, ...]] = set()
        if iterable is not None:
            for item in iterable:
                self.add(item)

    def _is_approx_equal(self, tuple1: Tuple[float, ...], tuple2: Tuple[float, ...]) -> bool:
        """Compare two tuples for approximate equality."""
        if len(tuple1) != len(tuple2):
            return False
        return all(abs(x - y) <= self.tolerance for x, y in zip(tuple1, tuple2))

    def _find_existing(self, item: Tuple[float, ...]) -> Tuple[float, ...] | None:
        """Find an existing item that approximately matches the given item."""
        return next(
            (
                existing_item
                for existing_item in self._data
                if self._is_approx_equal(existing_item, item)
            ),
            None,
        )

    def add(self, item: Tuple[float, ...]) -> None:
        if not self._find_existing(item):
            self._data.add(item)

    def discard(self, item: Tuple[float, ...]) -> None:
        if existing := self._find_existing(item):
            self._data.discard(existing)

    def __contains__(self, item: Tuple[float, ...]) -> bool:
        return self._find_existing(item) is not None

    def __iter__(self) -> Iterator[Tuple[float, ...]]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"ApproxSet({set(self)}, tolerance={self.tolerance})"
