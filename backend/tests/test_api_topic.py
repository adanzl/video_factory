import pytest

from app.api.errors import APIError
from app.api.utils import parse_int


def test_parse_int_default():
    assert parse_int({}, "count", 10, minimum=1, maximum=20) == 10


def test_parse_int_invalid():
    with pytest.raises(APIError):
        parse_int({"count": "x"}, "count", 10, minimum=1, maximum=20)
