"""网页搜索工具。"""

import os
from collections.abc import Iterable, Mapping
from typing import Any

from ddgs import DDGS
from langchain_core.tools import tool

from paotui.config import SearchToolConfig


def _format_results(results: Iterable[Mapping[str, Any]]) -> str:
    """把搜索结果排成文本。"""
    sections = []
    for index, result in enumerate(results, start=1):
        title = result.get("title", "（无标题）")
        url = result.get("href") or result.get("url") or "（无链接）"
        summary = result.get("body") or result.get("content") or "（无摘要）"
        sections.append(f"{index}. {title}\n{url}\n{summary}")
    return "\n\n".join(sections) if sections else "没搜到结果，换个关键词试试"


def _get_tavily_client_class() -> Any:
    """延迟导入 Tavily，让测试能替换这个工厂。"""
    from tavily import TavilyClient

    return TavilyClient


def make_search_tool(search_config: SearchToolConfig):
    """按配置建搜索工具。"""

    @tool
    def web_search(query: str) -> str:
        """搜网页，返回标题、链接和摘要。用来查公开资料。"""
        try:
            if search_config.backend == "ddgs":
                results = DDGS(timeout=10).text(query, max_results=search_config.max_results)
                return _format_results(results)

            try:
                tavily_client_class = _get_tavily_client_class()
            except ImportError:
                return "错误：未安装 Tavily 支持，请先安装 paotui[tavily]"
            api_key = os.environ.get("TAVILY_API_KEY")
            if not api_key:
                return "错误：未设置 TAVILY_API_KEY 环境变量"
            client = tavily_client_class(api_key=api_key)
            response = client.search(query, max_results=search_config.max_results)
            return _format_results(response.get("results", []))
        except Exception as error:
            if search_config.backend == "ddgs":
                return f"错误：搜索失败（{error}），免费搜索源可能暂时不稳定，请稍后重试"
            return f"错误：搜索失败（{error}）"

    return web_search
