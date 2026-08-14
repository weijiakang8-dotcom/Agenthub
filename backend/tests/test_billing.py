from app.core.billing import estimate_tokens


def test_estimate_tokens_positive():
    assert estimate_tokens("hello world") > 0
    assert estimate_tokens("") == 0


def test_estimate_tokens_monotonic():
    assert estimate_tokens("a" * 400) >= estimate_tokens("a" * 40)
