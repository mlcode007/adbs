#!/usr/bin/env python3
"""
本地拿到「像 uiautomator2.Device 一样的 d」，但底层走现有 /u2 HTTP 桥。

说明：这不是真正的 uiautomator2.Device（无法在本机直连 atx-agent），而是把桥的接口
封装成同名常用方法，便于脚本里写成 d.click / d.shell / d.screenshot。

依赖：仅标准库；若希望 screenshot() 返回与 u2 一致的 PIL 图，请 pip install pillow。

环境变量（可被参数覆盖）：
  U2_BASE、ADEVICE_SERIAL、U2_INSECURE_SSL=1

示例：
    from u2_bridge_device import connect

    d = connect(insecure=True)
    print(d.info)
    d.click(540, 1200)
    print(d.shell("getprop ro.product.model"))
    d.swipe(300, 800, 300, 200)
    im = d.screenshot()
    im.save("a.png")
    xml = d.dump_hierarchy()
    d.disconnect()
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO
from typing import Any


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _ssl_context(insecure: bool) -> ssl.SSLContext | None:
    return ssl._create_unverified_context() if insecure else None


class BridgeDevice:
    """通过 u2 HTTP 桥操作远端设备，用法刻意贴近 uiautomator2.Device 的常见调用。"""

    def __init__(
        self,
        serial: str,
        base: str,
        *,
        insecure: bool = False,
        timeout: float = 120.0,
    ) -> None:
        self._serial = serial.strip()
        self._base = base.rstrip("/")
        self._insecure = insecure
        self._timeout = timeout
        self._ctx = _ssl_context(insecure)
        self._info: dict[str, Any] | None = None
        self.session_connect()

    @property
    def serial(self) -> str:
        return self._serial

    @property
    def info(self) -> dict[str, Any]:
        if self._info is None:
            self.session_connect()
        assert self._info is not None
        return self._info

    def _url(self, path: str) -> str:
        path = path if path.startswith("/") else f"/{path}"
        return f"{self._base}{path}"

    def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = self._url(path)
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout, context=self._ctx) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    def _post_empty(self, path: str) -> dict[str, Any]:
        url = self._url(path)
        req = urllib.request.Request(url, data=b"{}", method="POST",
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self._timeout, context=self._ctx) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    def _get_bytes(self, path: str, query: dict[str, str]) -> bytes:
        q = urllib.parse.urlencode(query)
        url = f"{self._url(path)}?{q}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=self._timeout, context=self._ctx) as resp:
            return resp.read()

    def session_connect(self) -> dict[str, Any]:
        try:
            r = self._post_json("/session/connect", {"serial": self._serial})
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace")) from e
        self._info = r.get("info")
        return r

    def disconnect(self) -> None:
        q = urllib.parse.quote(self._serial, safe="")
        try:
            self._post_empty(f"/session/disconnect?serial={q}")
        except urllib.error.HTTPError:
            pass
        self._info = None

    def click(self, x: int, y: int) -> None:
        try:
            self._post_json("/click", {"serial": self._serial, "x": x, "y": y})
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace")) from e

    def click_text(self, text: str, timeout: float = 10.0) -> None:
        try:
            self._post_json(
                "/click_text",
                {"serial": self._serial, "text": text, "timeout": timeout},
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace")) from e

    def shell(self, command: str) -> str:
        try:
            r = self._post_json(
                "/shell",
                {"serial": self._serial, "command": command},
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace")) from e
        return str(r.get("output", ""))

    def swipe(
        self,
        sx: int,
        sy: int,
        ex: int,
        ey: int,
        duration: float = 0.5,
    ) -> None:
        try:
            self._post_json(
                "/swipe",
                {
                    "serial": self._serial,
                    "sx": sx,
                    "sy": sy,
                    "ex": ex,
                    "ey": ey,
                    "duration": duration,
                },
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace")) from e

    def screenshot_png_bytes(self) -> bytes:
        q = {"serial": self._serial, "png": "1"}
        try:
            return self._get_bytes("/screenshot", q)
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace")) from e

    def screenshot(self) -> Any:
        """与 u2 类似返回 PIL.Image；未安装 pillow 时抛出明确错误。"""
        try:
            from PIL import Image  # noqa: PLC0415
        except ImportError as e:
            raise RuntimeError(
                "screenshot() 需要 pillow：pip install pillow；或改用 screenshot_png_bytes()"
            ) from e
        data = self.screenshot_png_bytes()
        return Image.open(BytesIO(data)).convert("RGB")

    def dump_hierarchy(self) -> str:
        raw = self._get_bytes("/dump", {"serial": self._serial})
        return raw.decode("utf-8", errors="replace")

    def health(self) -> dict[str, Any]:
        url = self._url("/health")
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=30.0, context=self._ctx) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}

    def __repr__(self) -> str:
        return f"BridgeDevice(serial={self._serial!r}, base={self._base!r})"


def connect(
    serial: str | None = None,
    *,
    base: str | None = None,
    insecure: bool | None = None,
    timeout: float = 120.0,
) -> BridgeDevice:
    """
    构造本地可用的「桥接 d」，默认读环境变量 U2_BASE、ADEVICE_SERIAL。
    insecure 默认 None：为 None 时若 U2_INSECURE_SSL 为真则跳过 HTTPS 校验。
    """
    s = (serial or os.environ.get("ADEVICE_SERIAL", "")).strip()
    if not s:
        raise ValueError("请传入 serial= 或设置环境变量 ADEVICE_SERIAL")

    b = (base or os.environ.get("U2_BASE", "").strip()) or "http://127.0.0.1:18081/u2"

    inc = _env_bool("U2_INSECURE_SSL") if insecure is None else insecure

    return BridgeDevice(s, b, insecure=inc, timeout=timeout)


if __name__ == "__main__":
    import sys

    try:
        d = connect(insecure=True)
        d.click_text("首页", timeout=10)
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
    print(d.info)
    print(d.health())
