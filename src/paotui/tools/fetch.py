"""网页抓取工具。"""

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura
from langchain_core.tools import tool

from paotui.config import FetchToolConfig

_MAX_CONTENT_BYTES = 2 * 1024 * 1024
_MAX_REDIRECTS = 5
_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
_SUPPORTED_CONTENT_TYPES = ("text/html", "text/plain", "application/xhtml")

# 保留为模块级引用，方便离线测试替换为使用 MockTransport 的客户端。
HTTP_CLIENT_FACTORY = httpx.Client


def _check_url(url: str) -> str | None:
    """检查 URL 协议和解析出的地址，拦截内网地址以降低 SSRF 风险。"""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return "错误：URL 只支持 http 或 https 协议"
        if not parsed.hostname:
            return "错误：URL 缺少主机名"

        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or 443)
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                return "错误：URL 指向的地址不允许访问"
    except (OSError, ValueError) as error:
        return f"错误：无法安全解析 URL 主机名（{error}）"
    return None


def _truncate(text: str, max_chars: int) -> str:
    """截断超长正文，并向调用方说明。"""
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}\n（内容已截断，仅显示前 {max_chars} 个字符）"


def make_fetch_tool(fetch_config: FetchToolConfig):
    """按配置创建网页正文抓取工具。"""

    @tool
    def web_fetch(url: str) -> str:
        """抓取公开网页并提取为 Markdown 正文，适合阅读链接中的文章内容。"""
        current_url = url
        redirects = 0
        try:
            with HTTP_CLIENT_FACTORY(follow_redirects=False, timeout=15) as client:
                while True:
                    url_error = _check_url(current_url)
                    if url_error:
                        return url_error

                    # 校验与实际连接之间仍存在 DNS 重绑定竞态；个人本机用途可接受。
                    with client.stream("GET", current_url) as response:
                        if response.status_code in _REDIRECT_STATUS_CODES:
                            if redirects >= _MAX_REDIRECTS:
                                return "错误：重定向次数超过 5 跳"
                            location = response.headers.get("location")
                            if not location:
                                return "错误：重定向响应缺少目标地址"
                            next_url = urljoin(current_url, location)
                            url_error = _check_url(next_url)
                            if url_error:
                                return url_error
                            current_url = next_url
                            redirects += 1
                            continue

                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "").lower()
                        if not any(item in content_type for item in _SUPPORTED_CONTENT_TYPES):
                            return "错误：不支持的内容类型"

                        content_length = response.headers.get("content-length")
                        if content_length and int(content_length) > _MAX_CONTENT_BYTES:
                            return "错误：页面内容超过 2MB，拒绝抓取"

                        content = bytearray()
                        for chunk in response.iter_bytes():
                            content.extend(chunk)
                            if len(content) > _MAX_CONTENT_BYTES:
                                return "错误：页面内容超过 2MB，拒绝抓取"

                    html = bytes(content).decode(response.encoding or "utf-8", errors="replace")
                    if "text/plain" in content_type:
                        return _truncate(html, fetch_config.max_chars)

                    extracted = trafilatura.extract(html, output_format="markdown")
                    if extracted is None:
                        return "错误：没能从页面提取出正文（可能是纯 JS 渲染的页面）"
                    return _truncate(extracted, fetch_config.max_chars)
        except (httpx.HTTPError, OSError, ValueError) as error:
            return f"错误：抓取页面失败（{error}）"
        except Exception as error:
            return f"错误：处理页面失败（{error}）"

    return web_fetch
