"""
与 adbs 同机运行的 uiautomator2 HTTP 桥（建议仅监听回环口，由 Go 反向代理对外）。

对外统一只开 Go 的端口（默认 18081，环境变量 ADBS_PORT），Python 路径挂在其下前缀 /u2：
  http://<主机>:18081/u2/health
  http://<主机>:18081/u2/click  （等同下方 uvicorn 根路径 /click）

方式一（推荐，单一入口）：启动 Go 前设置环境变量自动拉起本服务（仅绑定本机）：
  export U2_AUTO_START=1
  go run .
  # 等价 uvicorn 监听 127.0.0.1:18082（可用 U2_INTERNAL_PORT 修改）

方式二：手动先起 uvicorn，再起 Go（无需 U2_AUTO_START）：
  cd python_u2_bridge && pip install -r requirements.txt
  uvicorn app:app --host 127.0.0.1 --port 18082
  # 另开终端 go run .  （Go 默认把 /u2 转发到 http://127.0.0.1:18082，可用 U2_BACKEND 覆盖）

原脚本改造示例：
  requests.post("http://主机:18081/u2/click", json={"serial":"...","x":100,"y":200})
"""

from __future__ import annotations

import io
import base64
from typing import Any

import uiautomator2 as u2
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

app = FastAPI(title="uiautomator2 HTTP bridge", version="0.1.0")

# serial -> Device（长连接会话；生产环境请加 TTL / 锁）
_devices: dict[str, Any] = {}


def get_device(serial: str):
    if serial not in _devices:
        try:
            _devices[serial] = u2.connect(serial)
        except Exception as e:
            raise HTTPException(502, detail=f"u2.connect failed: {e}") from e
    return _devices[serial]


class ConnectBody(BaseModel):
    serial: str = Field(..., description="adb serial，如 emulator-5554 或 192.168.1.10:5555")


@app.post("/session/connect")
def session_connect(body: ConnectBody):
    d = get_device(body.serial)
    info = d.info
    return {"ok": True, "serial": body.serial, "info": info}


@app.post("/session/disconnect")
def session_disconnect(serial: str = Query(...)):
    _devices.pop(serial, None)
    return {"ok": True}


class ClickBody(BaseModel):
    serial: str
    x: int
    y: int


@app.post("/click")
def click_xy(body: ClickBody):
    d = get_device(body.serial)
    d.click(body.x, body.y)
    return {"ok": True}


class TextClickBody(BaseModel):
    serial: str
    text: str
    timeout: float = 10.0
    contains: bool = Field(
        True,
        description="精确未命中时是否回退到 textContains 包含匹配；False 则只做精确匹配",
    )


@app.post("/click_text")
def click_text(body: TextClickBody):
    d = get_device(body.serial)

    el = d(text=body.text)
    if el.wait(timeout=body.timeout):
        el.click()
        return {"ok": True, "matched_by": "text"}

    if body.contains:
        el2 = d(textContains=body.text)
        if el2.exists:
            el2.click()
            return {"ok": True, "matched_by": "textContains"}

    # 收集页面上现有 text，便于调试为什么没匹配上
    similar: list[str] = []
    try:
        xml = d.dump_hierarchy()
        import re

        seen: set[str] = set()
        for m in re.finditer(r'text="([^"]*)"', xml):
            t = m.group(1)
            if t and t not in seen:
                seen.add(t)
                if body.text and body.text in t:
                    similar.append(t)
        if not similar:
            similar = [t for t in seen if t][:20]
    except Exception:
        pass

    raise HTTPException(
        404,
        detail={
            "message": f'no widget text="{body.text}"',
            "contains_tried": body.contains,
            "similar_or_visible_texts": similar,
        },
    )


class ShellBody(BaseModel):
    serial: str
    command: str


@app.post("/shell")
def adb_shell(body: ShellBody):
    d = get_device(body.serial)
    out = d.shell(body.command)
    return {"ok": True, "output": out}


@app.get("/screenshot")
def screenshot(serial: str = Query(...), png: bool = True):
    d = get_device(serial)
    im = d.screenshot()
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    data = buf.getvalue()
    if png:
        return Response(content=data, media_type="image/png")
    return {"ok": True, "image_base64": base64.b64encode(data).decode("ascii")}


@app.get("/dump")
def dump_hierarchy(serial: str = Query(...)):
    d = get_device(serial)
    xml = d.dump_hierarchy()
    return Response(content=xml, media_type="application/xml")


class SwipeBody(BaseModel):
    serial: str
    sx: int
    sy: int
    ex: int
    ey: int
    duration: float = 0.5


@app.post("/swipe")
def swipe(body: SwipeBody):
    d = get_device(body.serial)
    d.swipe(body.sx, body.sy, body.ex, body.ey, body.duration)
    return {"ok": True}


class SelectorBody(BaseModel):
    serial: str
    selector: dict[str, Any] = Field(
        ...,
        description='u2 选择器关键字参数，例如 {"text":"首页"} 或 {"resourceId":"com.x:id/y"}',
    )
    timeout: float = 10.0


@app.post("/exists")
def selector_exists(body: SelectorBody):
    """按 u2 选择器判断元素当前是否存在（不等待）。"""
    d = get_device(body.serial)
    try:
        ok = bool(d(**body.selector).exists)
    except Exception as e:
        raise HTTPException(400, detail=f"bad selector: {e}") from e
    return {"ok": True, "exists": ok}


@app.post("/wait")
def selector_wait(body: SelectorBody):
    """按 u2 选择器等待元素出现，返回 found=true/false。"""
    d = get_device(body.serial)
    try:
        found = bool(d(**body.selector).wait(timeout=body.timeout))
    except Exception as e:
        raise HTTPException(400, detail=f"bad selector: {e}") from e
    return {"ok": True, "found": found}


class TextBody(BaseModel):
    serial: str
    text: str
    timeout: float = 10.0
    contains: bool = Field(
        True,
        description="精确未命中时是否回退到 textContains 包含匹配；False 则只做精确匹配",
    )


@app.post("/has_text")
def has_text(body: TextBody):
    """当前界面是否包含给定文本（不等待）。

    返回 ``matched_by`` 指明命中方式：``text`` / ``textContains`` / ``none``。
    """
    d = get_device(body.serial)
    if bool(d(text=body.text).exists):
        return {"ok": True, "exists": True, "matched_by": "text"}
    if body.contains and bool(d(textContains=body.text).exists):
        return {"ok": True, "exists": True, "matched_by": "textContains"}
    return {"ok": True, "exists": False, "matched_by": "none"}


@app.post("/wait_text")
def wait_text(body: TextBody):
    """等待给定文本出现，返回 found=true/false。

    精确等待未命中且 ``contains=true`` 时，会再用 ``textContains`` 立即判断一次。
    """
    d = get_device(body.serial)
    if bool(d(text=body.text).wait(timeout=body.timeout)):
        return {"ok": True, "found": True, "matched_by": "text"}
    if body.contains and bool(d(textContains=body.text).exists):
        return {"ok": True, "found": True, "matched_by": "textContains"}
    return {"ok": True, "found": False, "matched_by": "none"}


class XPathBody(BaseModel):
    serial: str
    xpath: str
    action: str = Field(
        "exists",
        description="exists | wait | click | get_text | info | all",
    )
    timeout: float = 10.0


@app.post("/xpath")
def xpath_action(body: XPathBody):
    """对 XPath 表达式执行常用动作。

    action：
      - exists   立即返回 {exists: bool}
      - wait     在 timeout 内等待，返回 {found: bool}
      - click    在 timeout 内等待并点击；找不到 → 404
      - get_text 在 timeout 内等待并取文本；找不到 → 404
      - info     在 timeout 内等待并返回节点 info；找不到 → 404
      - all      返回所有匹配节点 info 列表
    """
    d = get_device(body.serial)
    try:
        x = d.xpath(body.xpath)
    except Exception as e:
        raise HTTPException(400, detail=f"bad xpath: {e}") from e

    act = (body.action or "exists").strip().lower()
    if act == "exists":
        return {"ok": True, "exists": bool(x.exists)}
    if act == "wait":
        return {"ok": True, "found": bool(x.wait(timeout=body.timeout))}
    if act == "click":
        if not x.wait(timeout=body.timeout):
            raise HTTPException(404, detail=f"no node matched xpath: {body.xpath}")
        x.click()
        return {"ok": True}
    if act == "get_text":
        if not x.wait(timeout=body.timeout):
            raise HTTPException(404, detail=f"no node matched xpath: {body.xpath}")
        return {"ok": True, "text": x.get_text()}
    if act == "info":
        el = x.wait(timeout=body.timeout)
        if not el:
            raise HTTPException(404, detail=f"no node matched xpath: {body.xpath}")
        info = getattr(el, "info", None)
        if info is None:
            info = dict(getattr(el, "attrib", {}) or {})
        return {"ok": True, "info": info}
    if act == "all":
        nodes = x.all() or []
        items = []
        for n in nodes:
            info = getattr(n, "info", None)
            if info is None:
                info = dict(getattr(n, "attrib", {}) or {})
            items.append(info)
        return {"ok": True, "count": len(items), "items": items}
    raise HTTPException(400, detail=f"unknown action: {body.action}")


def _parse_mode(mode: str) -> int:
    """允许八进制 0o644 / 十六进制 0x1A4 / 纯数字字符串 644 (按八进制) / 0 前缀八进制。"""
    m = (mode or "").strip()
    if not m:
        return 0o644
    try:
        if m.startswith(("0o", "0O")):
            return int(m, 8)
        if m.startswith(("0x", "0X")):
            return int(m, 16)
        if m.isdigit():
            return int(m, 8)
        return int(m, 0)
    except ValueError:
        return 0o644


@app.post("/push")
async def push_file(
    serial: str = Form(..., description="adb serial"),
    dst: str = Form(..., description="设备端目标绝对路径"),
    mode: str = Form("0o644", description="权限：0o644 / 0x1A4 / 644 等"),
    file: UploadFile = File(..., description="要上传的文件"),
):
    """将上传文件 PUSH 到设备端 dst 路径。"""
    d = get_device(serial)
    data = await file.read()
    perm = _parse_mode(mode)
    try:
        d.push(io.BytesIO(data), dst, mode=perm)
    except Exception as e:
        raise HTTPException(502, detail=f"push failed: {e}") from e
    return {
        "ok": True,
        "dst": dst,
        "size": len(data),
        "mode": oct(perm),
        "filename": file.filename,
    }


@app.get("/health")
def health():
    return {"ok": True, "sessions": list(_devices.keys())}
