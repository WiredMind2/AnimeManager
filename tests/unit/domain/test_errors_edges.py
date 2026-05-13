"""Edge case tests for ``domain.errors``.

Confirms the error hierarchy contracts used by the application layer.
"""

from __future__ import annotations

import pickle

import pytest

from domain.errors import (
    AnimeManagerError,
    InfrastructureError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)


class TestErrorHierarchy:
    @pytest.mark.parametrize(
        "cls",
        [NotFoundError, ValidationError, InfrastructureError, UnauthorizedError],
    )
    def test_all_subclass_base(self, cls):
        assert issubclass(cls, AnimeManagerError)
        assert issubclass(cls, Exception)

    def test_can_be_raised_and_caught_as_base(self):
        with pytest.raises(AnimeManagerError):
            raise NotFoundError("missing")

    def test_message_preserved(self):
        try:
            raise ValidationError("bad input")
        except ValidationError as exc:
            assert str(exc) == "bad input"
            assert exc.args == ("bad input",)

    def test_no_args(self):
        with pytest.raises(NotFoundError):
            raise NotFoundError()

    @pytest.mark.parametrize(
        "cls",
        [
            AnimeManagerError,
            NotFoundError,
            ValidationError,
            InfrastructureError,
            UnauthorizedError,
        ],
    )
    def test_picklable(self, cls):
        exc = cls("oops")
        roundtripped = pickle.loads(pickle.dumps(exc))
        assert isinstance(roundtripped, cls)
        assert str(roundtripped) == "oops"

    def test_distinct_types(self):
        # NotFoundError must not be caught as ValidationError and vice versa
        with pytest.raises(NotFoundError):
            try:
                raise NotFoundError("x")
            except ValidationError:  # pragma: no cover - control flow only
                raise AssertionError("Should not match")
