from app.core.notification import render_template


def test_render_template_substitutes_vars():
    text = render_template("alert", {"message": "hello"})
    assert text == "告警：hello"


def test_render_execution_template():
    text = render_template(
        "execution_completed",
        {"execution_id": "abc", "status": "completed"},
    )
    assert "abc" in text
    assert "completed" in text
