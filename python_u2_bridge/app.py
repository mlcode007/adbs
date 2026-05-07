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
from fastapi import FastAPI, HTTPException, Query
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


@app.post("/click_text")
def click_text(body: TextClickBody):
    d = get_device(body.serial)
    el = d(text=body.text)
    if not el.wait(timeout=body.timeout):
        raise HTTPException(404, detail=f'no widget text="{body.text}"')
    el.click()
    return {"ok": True}


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


@app.get("/health")
def health():
    return {"ok": True, "sessions": list(_devices.keys())}
