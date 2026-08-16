from app.core.circuit_breaker import CircuitBreaker


def test_breaker_opens_after_failure_threshold():
    breaker = CircuitBreaker(failure_threshold=2, window=60, cooldown=60)

    breaker.record_failure()
    assert breaker.allow() is True

    breaker.record_failure()
    assert breaker.allow() is False


def test_success_closes_breaker():
    breaker = CircuitBreaker(failure_threshold=1, window=60, cooldown=60)

    breaker.record_failure()
    assert breaker.allow() is False

    breaker.record_success()
    assert breaker.allow() is True
