"""微信 API 错误分层与敏感信息脱敏。"""

from __future__ import annotations

import re
from collections.abc import Iterable


_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(access_token|token|secret)(\s*[=:]\s*)([^\s&]+)"
)


def redact(value: object, secrets: Iterable[str] = ()) -> str:
    """隐藏已知敏感值与常见 token/secret 赋值片段。"""

    text = str(value)
    for secret in sorted((item for item in secrets if item), key=len, reverse=True):
        text = text.replace(secret, "***")
    return _SENSITIVE_ASSIGNMENT.sub(r"\1\2***", text)


class WechatError(RuntimeError):
    """所有可安全展示的微信调用错误基类。"""


class WechatTransportError(WechatError):
    def __init__(self, endpoint: str, detail: object, secrets: Iterable[str] = ()) -> None:
        super().__init__(f"微信接口传输失败 endpoint={endpoint}: {redact(detail, secrets)}")


class UncertainStateError(WechatTransportError):
    def __init__(self, endpoint: str, detail: object, secrets: Iterable[str] = ()) -> None:
        WechatError.__init__(
            self,
            f"微信接口传输失败，状态不确定，勿直接重试 endpoint={endpoint}: "
            f"{redact(detail, secrets)}",
        )


class WechatHTTPError(WechatError):
    def __init__(
        self, endpoint: str, status_code: int, detail: object, secrets: Iterable[str] = ()
    ) -> None:
        self.status_code = status_code
        super().__init__(
            f"微信接口 HTTP 状态异常 endpoint={endpoint} status={status_code}: "
            f"{redact(detail, secrets)}"
        )


class WechatResponseError(WechatError):
    def __init__(self, endpoint: str, detail: object, secrets: Iterable[str] = ()) -> None:
        super().__init__(f"微信接口响应格式异常 endpoint={endpoint}: {redact(detail, secrets)}")


class WechatAPIError(WechatError):
    def __init__(
        self,
        endpoint: str,
        errcode: int,
        errmsg: object,
        secrets: Iterable[str] = (),
    ) -> None:
        self.errcode = errcode
        super().__init__(
            f"微信接口业务错误 endpoint={endpoint} errcode={errcode} "
            f"errmsg={redact(errmsg, secrets)}"
        )

