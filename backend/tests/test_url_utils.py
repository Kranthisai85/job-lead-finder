import pytest

from app.utils.url import normalize_website


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://abc.com/", "abc.com"),
        ("https://abc.com", "abc.com"),
        ("http://abc.com", "abc.com"),
        ("  https://www.abc.com/path  ", "abc.com"),
    ],
)
def test_normalize_website(raw: str, expected: str) -> None:
    assert normalize_website(raw) == expected
