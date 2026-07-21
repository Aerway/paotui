import sys
import types

from paotui.config import SearchToolConfig
from paotui.tools import search


def invoke(tool: object, query: str) -> str:
    """调用搜索工具并取得字符串结果。"""
    return tool.invoke({"query": query})  # type: ignore[union-attr]


def test_ddgs_results_are_formatted(monkeypatch) -> None:
    class FakeDDGS:
        def __init__(self, timeout: int) -> None:
            assert timeout == 10

        def text(self, query: str, max_results: int) -> list[dict[str, str]]:
            assert query == "测试关键词"
            assert max_results == 2
            return [
                {"title": "第一条", "href": "https://one.example", "body": "摘要一"},
                {"title": "第二条", "href": "https://two.example", "body": "摘要二"},
            ]

    monkeypatch.setattr(search, "DDGS", FakeDDGS)
    tool = search.make_search_tool(SearchToolConfig(max_results=2))

    result = invoke(tool, "测试关键词")

    assert "1. 第一条\nhttps://one.example\n摘要一" in result
    assert "2. 第二条\nhttps://two.example\n摘要二" in result


def test_ddgs_empty_result_has_hint(monkeypatch) -> None:
    class FakeDDGS:
        def __init__(self, timeout: int) -> None:
            pass

        def text(self, query: str, max_results: int) -> list[dict[str, str]]:
            return []

    monkeypatch.setattr(search, "DDGS", FakeDDGS)

    assert "没搜到" in invoke(search.make_search_tool(SearchToolConfig()), "不存在")


def test_ddgs_error_is_returned(monkeypatch) -> None:
    class FakeDDGS:
        def __init__(self, timeout: int) -> None:
            pass

        def text(self, query: str, max_results: int) -> list[dict[str, str]]:
            raise RuntimeError("服务不可用")

    monkeypatch.setattr(search, "DDGS", FakeDDGS)

    result = invoke(search.make_search_tool(SearchToolConfig()), "测试")

    assert result.startswith("错误：搜索失败")
    assert "稍后重试" in result


def test_tavily_missing_package_has_install_hint(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "tavily", None)
    tool = search.make_search_tool(SearchToolConfig(backend="tavily"))

    result = invoke(tool, "测试")

    assert "paotui[tavily]" in result


def test_tavily_missing_api_key_has_hint(monkeypatch) -> None:
    fake_module = types.ModuleType("tavily")

    class FakeTavilyClient:
        pass

    fake_module.TavilyClient = FakeTavilyClient
    monkeypatch.setitem(sys.modules, "tavily", fake_module)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    tool = search.make_search_tool(SearchToolConfig(backend="tavily"))

    assert "TAVILY_API_KEY" in invoke(tool, "测试")
