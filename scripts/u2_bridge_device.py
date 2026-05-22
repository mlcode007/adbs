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

    # 等待 / 判断
    d.has_text("首页")
    d.wait_text("登录", timeout=10)
    d(text="首页").exists
    d(resourceId="com.x:id/y").wait(timeout=5)

    # XPath
    d.xpath('//*[@text="首页"]').click()
    print(d.xpath('//*[@resource-id="com.x:id/title"]').get_text())

    # 推送文件
    d.push("./a.apk", "/sdcard/Download/a.apk", mode=0o644)

    d.disconnect()
"""

from __future__ import annotations

import json
import mimetypes
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
import uuid
from io import BytesIO
from pathlib import Path
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

    def _post_multipart(
        self,
        path: str,
        fields: dict[str, str],
        file_field: str,
        filename: str,
        filedata: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        boundary = f"----adbsboundary{uuid.uuid4().hex}"
        parts: list[bytes] = []
        for k, v in fields.items():
            parts.append(f"--{boundary}\r\n".encode())
            parts.append(
                f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
            )
            parts.append(str(v).encode("utf-8"))
            parts.append(b"\r\n")
        parts.append(f"--{boundary}\r\n".encode())
        parts.append(
            (
                f'Content-Disposition: form-data; name="{file_field}"; '
                f'filename="{filename}"\r\n'
            ).encode()
        )
        parts.append(f"Content-Type: {content_type}\r\n\r\n".encode())
        parts.append(filedata)
        parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        req = urllib.request.Request(
            self._url(path),
            data=body,
            method="POST",
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Content-Length": str(len(body)),
            },
        )
        with urllib.request.urlopen(req, timeout=self._timeout, context=self._ctx) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}

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

    def click_text(
        self,
        text: str,
        timeout: float = 10.0,
        contains: bool = True,
    ) -> dict[str, Any]:
        """点击文本控件。

        - ``contains=True``（默认）：精确未命中时桥服务端会回退到 ``textContains`` 包含匹配。
        - ``contains=False``：仅做精确匹配，与旧行为一致。

        返回服务端 JSON，含 ``matched_by``（``text`` / ``textContains``）。
        """
        try:
            return self._post_json(
                "/click_text",
                {
                    "serial": self._serial,
                    "text": text,
                    "timeout": timeout,
                    "contains": contains,
                },
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

    def exists(self, **selector: Any) -> bool:
        """按 u2 选择器判断元素当前是否存在（不等待）。

        例：``d.exists(text="首页")`` / ``d.exists(resourceId="com.x:id/y")``
        """
        try:
            r = self._post_json(
                "/exists",
                {"serial": self._serial, "selector": selector},
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace")) from e
        return bool(r.get("exists"))

    def wait(self, timeout: float = 10.0, **selector: Any) -> bool:
        """按 u2 选择器在 ``timeout`` 内等待元素出现，返回是否找到。"""
        try:
            r = self._post_json(
                "/wait",
                {"serial": self._serial, "selector": selector, "timeout": timeout},
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace")) from e
        return bool(r.get("found"))

    def has_text(self, text: str, contains: bool = True) -> bool:
        """当前界面是否包含给定文本（不等待）。

        ``contains=True`` 时桥服务端会在精确未命中后再尝试包含匹配。
        """
        try:
            r = self._post_json(
                "/has_text",
                {"serial": self._serial, "text": text, "contains": contains},
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace")) from e
        return bool(r.get("exists"))

    def wait_text(
        self,
        text: str,
        timeout: float = 10.0,
        contains: bool = True,
    ) -> bool:
        """等待给定文本出现，返回是否找到。

        ``contains=True`` 时精确等待失败会再用包含匹配判断一次。
        """
        try:
            r = self._post_json(
                "/wait_text",
                {
                    "serial": self._serial,
                    "text": text,
                    "timeout": timeout,
                    "contains": contains,
                },
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace")) from e
        return bool(r.get("found"))

    def xpath_action(
        self,
        xpath: str,
        action: str = "exists",
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """对 XPath 直接执行一次动作（exists/wait/click/get_text/info/all），返回服务端 JSON。

        通常更推荐使用 ``d.xpath(expr).click()`` 链式调用。
        """
        try:
            return self._post_json(
                "/xpath",
                {
                    "serial": self._serial,
                    "xpath": xpath,
                    "action": action,
                    "timeout": timeout,
                },
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace")) from e

    def push(
        self,
        src: str | bytes | os.PathLike[str] | BytesIO,
        dst: str,
        mode: int | str = 0o644,
    ) -> dict[str, Any]:
        """把本地文件 / 内存字节 PUSH 到设备 ``dst``。

        - ``src`` 支持本地路径字符串、``PathLike``、``bytes`` 或 ``BytesIO``。
        - ``mode`` 接受 ``int``（如 ``0o644``）或字符串（``"0o644"`` / ``"644"`` / ``"0x1A4"``）。
        """
        if isinstance(src, (bytes, bytearray)):
            data = bytes(src)
            filename = os.path.basename(dst) or "blob"
            ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        elif isinstance(src, BytesIO):
            data = src.getvalue()
            filename = os.path.basename(dst) or "blob"
            ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        else:
            p = Path(os.fspath(src))
            data = p.read_bytes()
            filename = p.name
            ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"

        mode_str = mode if isinstance(mode, str) else oct(int(mode))
        try:
            return self._post_multipart(
                "/push",
                {"serial": self._serial, "dst": dst, "mode": mode_str},
                file_field="file",
                filename=filename,
                filedata=data,
                content_type=ctype,
            )
        except urllib.error.HTTPError as e:
            raise RuntimeError(e.read().decode(errors="replace")) from e

    def __call__(self, **selector: Any) -> "_Selector":
        """模拟 u2 的 ``d(text="x")``，返回带 ``.exists`` / ``.wait()`` / ``.click()`` 的代理。"""
        return _Selector(self, selector)

    def xpath(self, xpath: str) -> "_XPath":
        """模拟 u2 的 ``d.xpath('//x')``，返回支持链式动作的代理。"""
        return _XPath(self, xpath)

    def __repr__(self) -> str:
        return f"BridgeDevice(serial={self._serial!r}, base={self._base!r})"


class _Selector:
    """轻量选择器代理，仅封装 /exists、/wait 与 /click_text（当选择器仅含 text 时）。"""

    def __init__(self, dev: BridgeDevice, selector: dict[str, Any]) -> None:
        self._dev = dev
        self._sel = selector

    @property
    def exists(self) -> bool:
        return self._dev.exists(**self._sel)

    def wait(self, timeout: float = 10.0) -> bool:
        return self._dev.wait(timeout=timeout, **self._sel)

    def click(self, timeout: float = 10.0) -> None:
        text = self._sel.get("text")
        if text is not None and len(self._sel) == 1:
            self._dev.click_text(text, timeout=timeout)
            return
        raise NotImplementedError(
            "桥服务端目前仅支持 text 选择器的点击，请使用 d.xpath(...).click() 或 d.click_text(...)"
        )

    def __repr__(self) -> str:
        return f"_Selector({self._sel!r})"


class _XPath:
    """XPath 代理，封装 /xpath 的各种 action。"""

    def __init__(self, dev: BridgeDevice, xpath: str) -> None:
        self._dev = dev
        self._xpath = xpath

    @property
    def exists(self) -> bool:
        r = self._dev.xpath_action(self._xpath, action="exists")
        return bool(r.get("exists"))

    def wait(self, timeout: float = 10.0) -> bool:
        r = self._dev.xpath_action(self._xpath, action="wait", timeout=timeout)
        return bool(r.get("found"))

    def click(self, timeout: float = 10.0) -> None:
        self._dev.xpath_action(self._xpath, action="click", timeout=timeout)

    def get_text(self, timeout: float = 10.0) -> str:
        r = self._dev.xpath_action(self._xpath, action="get_text", timeout=timeout)
        return str(r.get("text", ""))

    def info(self, timeout: float = 10.0) -> dict[str, Any]:
        r = self._dev.xpath_action(self._xpath, action="info", timeout=timeout)
        return dict(r.get("info") or {})

    def all(self) -> list[dict[str, Any]]:
        r = self._dev.xpath_action(self._xpath, action="all")
        return list(r.get("items") or [])

    def __repr__(self) -> str:
        return f"_XPath({self._xpath!r})"


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
        base_url = 'https://caiji-adb-console-itoamms.smzdm.com/u2'
        serial = '10.131.14.5'
        d = connect(serial=serial, base=base_url, insecure=True)
        d.click_text("首页", timeout=10)
        # d.screenshot()
    except ValueError as e:
        print(e, file=sys.stderr)
        sys.exit(2)
    print(d.info)
    print(d.health())
