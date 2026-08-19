from __future__ import annotations

from app.core.failure import ErrorCategory, classify_error, should_retry


def test_provider_timeout_is_handled_by_llm_layer_not_celery():
    category = classify_error(TimeoutError("llm request timed out"))
    assert category == ErrorCategory.TIMEOUT
    assert should_retry(category, "llm") is True
    assert should_retry(category, "celery") is False


def test_infrastructure_failure_is_celery_layer():
    category = classify_error(RuntimeError("database unavailable"))
    assert category == ErrorCategory.INFRASTRUCTURE
    assert should_retry(category, "celery") is True


def test_business_failure_never_retries():
    category = classify_error(RuntimeError("user request cannot be fulfilled"))
    assert category == ErrorCategory.BUSINESS
    assert should_retry(category, "celery") is False
    assert should_retry(category, "llm") is False
