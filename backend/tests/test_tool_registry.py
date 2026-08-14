from app.engine.tool_registry import get_tool, list_tools, unregister_tool


def test_builtin_tools_registered():
    names = {tool["name"] for tool in list_tools()}
    assert {"search_web", "query_db", "send_email"} <= names


def test_get_tool_returns_spec():
    spec = get_tool("search_web")
    assert spec is not None
    assert spec.name == "search_web"


def test_unregister_unknown_tool():
    assert unregister_tool("does-not-exist") is False
