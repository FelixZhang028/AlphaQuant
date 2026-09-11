"""Credential-safe diagnostics and bounded, nontechnical user messages."""

import re
from urllib.parse import urlsplit, urlunsplit

_SECRET = r"(?:[\w-]*(?:token|password|passwd|secret|api[_-]?key)|authorization|cookie)"


def redact_text(value: object) -> str:
    text = str(value)

    def clean_url(match: re.Match) -> str:
        try:
            url = urlsplit(match.group())
            host = url.netloc.rsplit("@", 1)[-1]
            return urlunsplit((url.scheme, host, url.path, "", ""))
        except ValueError:
            return "[请求地址已隐藏]"

    text = re.sub(r"https?://[^\s\"'<>]+", clean_url, text)
    text = re.sub(r"(?i)\bBearer\s+[^\s,;\"']+", "Bearer [REDACTED]", text)
    return re.sub(
        rf"(?i)(\b{_SECRET}[\"']?\s*[:=]\s*)(?:\"[^\"]*\"|'[^']*'|[^\s&,;}}]+)",
        r"\1[REDACTED]",
        text,
    )


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if re.fullmatch(_SECRET, str(key), re.I) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return redact_text(value) if isinstance(value, str) else value


def public_data_error(error: object) -> str:
    """Never return arbitrary exception text, URLs, or response bodies."""
    message = str(error).lower()
    if any(x in message for x in ("401", "unauthorized", "认证未通过", "token 未配置")):
        return "数据源认证未通过，请在设置中检查凭证。"
    if any(x in message for x in ("403", "forbidden", "权限不足")):
        return "数据源访问权限不足，请检查接口授权。"
    if any(x in message for x in ("429", "too many requests", "请求过于频繁")):
        return "请求过于频繁，请稍后重试。"
    if any(x in message for x in ("timeout", "timed out", "超时")):
        return "数据源响应超时，请稍后重试。"
    if any(x in message for x in ("connection", "proxy", "network", "网络连接")):
        return "数据源网络连接失败，请检查网络后重试。"
    if any(x in message for x in ("no daily bars", "no benchmark bars", "无数据")):
        return "所选范围无数据，请检查日期和证券代码。"
    return "数据更新失败，请稍后重试；持续失败请联系维护人员。"
