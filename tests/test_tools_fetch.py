import socket

import httpx

from paotui.config import FetchToolConfig
from paotui.tools import fetch


def _address(ip: str) -> tuple[int, int, int, str, tuple[str, int]]:
    return (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))


def _install_resolver(monkeypatch, addresses: dict[str, str]) -> None:
    """把 DNS 解析换成离线替身。"""
    def fake_getaddrinfo(host: str, port: int):
        return [_address(addresses[host])]

    monkeypatch.setattr(fetch.socket, "getaddrinfo", fake_getaddrinfo)


def _make_tool(monkeypatch, handler, max_chars: int = 20_000):
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        fetch,
        "HTTP_CLIENT_FACTORY",
        lambda **kwargs: httpx.Client(transport=transport, **kwargs),
    )
    return fetch.make_fetch_tool(FetchToolConfig(max_chars=max_chars))


def invoke(tool: object, url: str) -> str:
    return tool.invoke({"url": url})  # type: ignore[union-attr]


def test_check_url_rejects_unsafe_addresses_and_protocol(monkeypatch) -> None:
    _install_resolver(
        monkeypatch,
        {
            "127.0.0.1": "127.0.0.1",
            "localhost": "127.0.0.1",
            "10.0.0.5": "10.0.0.5",
            "169.254.169.254": "169.254.169.254",
        },
    )

    for url in (
        "http://127.0.0.1/",
        "http://localhost/x",
        "http://10.0.0.5/",
        "http://169.254.169.254/",
        "ftp://a.com",
    ):
        assert fetch._check_url(url) is not None


def test_check_url_allows_public_address(monkeypatch) -> None:
    _install_resolver(monkeypatch, {"example.test": "93.184.216.34"})

    assert fetch._check_url("https://example.test/article") is None


def test_fetch_html_extracts_body_without_network(monkeypatch) -> None:
    _install_resolver(monkeypatch, {"example.test": "93.184.216.34"})
    html = """
    <html><head><title>示例</title></head><body>
      <article><h1>文章标题</h1><p>这是需要提取的正文文字。</p><p>第二段内容。</p></article>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "example.test"
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    result = invoke(_make_tool(monkeypatch, handler), "https://example.test/article")

    assert "这是需要提取的正文文字" in result


def test_fetch_rejects_redirect_to_private_address(monkeypatch) -> None:
    _install_resolver(
        monkeypatch,
        {"example.test": "93.184.216.34", "127.0.0.1": "127.0.0.1"},
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/"})

    result = invoke(_make_tool(monkeypatch, handler), "https://example.test/article")

    assert result.startswith("错误：")
    assert "不允许访问" in result


def test_fetch_rejects_unsupported_content_type(monkeypatch) -> None:
    _install_resolver(monkeypatch, {"example.test": "93.184.216.34"})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"pdf")

    result = invoke(_make_tool(monkeypatch, handler), "https://example.test/document")

    assert result == "错误：不支持的内容类型"


def test_fetch_rejects_large_content_length(monkeypatch) -> None:
    _install_resolver(monkeypatch, {"example.test": "93.184.216.34"})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html", "content-length": str(2 * 1024 * 1024 + 1)},
        )

    result = invoke(_make_tool(monkeypatch, handler), "https://example.test/large")

    assert result == "错误：页面内容超过 2MB，拒绝抓取"


def test_fetch_truncates_long_content(monkeypatch) -> None:
    _install_resolver(monkeypatch, {"example.test": "93.184.216.34"})
    html = f"<html><body><article><p>{'正文内容。' * 100}</p></article></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=html)

    result = invoke(_make_tool(monkeypatch, handler, max_chars=50), "https://example.test/long")

    assert "内容已截断" in result
