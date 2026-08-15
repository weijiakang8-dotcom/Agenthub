from app.core.safe_expression import evaluate_condition


def test_empty_expression_is_true():
    assert evaluate_condition("", {"final_output": ""}) is True
    assert evaluate_condition(None, {}) is True


def test_supported_comparisons_and_functions():
    context = {
        "final_output": "hello world",
        "messages": ["a", "b", "c"],
        "node_outputs": {"n1": "ok"},
    }

    assert evaluate_condition("len(final_output) > 5", context) is True
    assert evaluate_condition('"world" in final_output', context) is True
    assert evaluate_condition('node_outputs["n1"] == "ok"', context) is True
    assert evaluate_condition("len(messages) >= 3 and final_output", context) is True
    assert evaluate_condition("not final_output", context) is False


def test_invalid_expression_returns_false():
    context = {"final_output": "hello"}

    assert evaluate_condition("__import__('os').system('id')", context) is False
    assert evaluate_condition("().__class__.__mro__[1].__subclasses__()", context) is False
    assert evaluate_condition("final_output.__class__", context) is False
    assert evaluate_condition("open('/etc/passwd')", context) is False


def test_missing_name_returns_false():
    assert evaluate_condition("unknown_variable", {}) is False
