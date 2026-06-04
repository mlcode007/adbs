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

会话模型：
  无状态——每个 HTTP 请求都会重新 ``u2.connect(serial)``，请求结束即释放底层 HTTP client。
  好处是不会出现"缓存里那个 Device 已经废了但服务端不知道"的僵尸会话问题；
  代价是每个请求多 0.3 ~ 2s 的握手开销。需要频繁/低延迟操作时建议改回带缓存模式。

可调环境变量：
  U2_CONNECT_TIMEOUT     u2.connect(serial) 单次最长耗时，默认 15 秒
  U2_CALL_TIMEOUT        单个设备方法调用最长耗时，默认 30 秒
  U2_EXECUTOR_WORKERS    内部线程池大小，默认 32
                         调参建议：约等于 "同时在用的手机数 × 2~3"
                           5~10 台手机 → 24~32
                          10~20 台手机 → 48~64
                              更多 → 直接上多 worker / 加机器
  U2_ANYIO_POOL_TOKENS   Starlette 外层线程池上限，默认 = U2_EXECUTOR_WORKERS × 2
                         FastAPI 跑 sync def 用的池子，要 ≥ 内层池才不会成为新瓶颈

原脚本改造示例：
  requests.post("http://主机:18081/u2/click", json={"serial":"...","x":100,"y":200})
"""

from __future__ import annotations

import base64
import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from contextlib import contextmanager
from typing import Any, Iterator

import anyio
import uiautomator2 as u2
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

logger = logging.getLogger("u2_bridge")

app = FastAPI(title="uiautomator2 HTTP bridge", version="0.2.0")


CONNECT_TIMEOUT = float(os.environ.get("U2_CONNECT_TIMEOUT", "15"))
CALL_TIMEOUT = float(os.environ.get("U2_CALL_TIMEOUT", "30"))
_EXECUTOR_WORKERS = max(1, int(os.environ.get("U2_EXECUTOR_WORKERS", "32")))
# 外层 Starlette/AnyIO 线程池：默认是内层的两倍，留排队 buffer
_ANYIO_POOL_TOKENS = max(
    _EXECUTOR_WORKERS,
    int(os.environ.get("U2_ANYIO_POOL_TOKENS", str(_EXECUTOR_WORKERS * 2))),
)

# 注意：每个请求都会新建/销毁 Device；线程池只用来给阻塞调用加超时，不持有会话。
_executor = ThreadPoolExecutor(
    max_workers=_EXECUTOR_WORKERS, thread_name_prefix="u2bridge"
)


@app.on_event("startup")
def _tune_anyio_threadpool() -> None:
    """把 Starlette 默认线程池上限调到与 _executor 匹配。

    FastAPI 跑 sync def 路由用的是 AnyIO 默认线程池（上限默认 40）。
    内层 _executor 若大于 40，外层就成新瓶颈。这里启动时统一拉齐，
    避免线上调大 U2_EXECUTOR_WORKERS 时被外层"暗地里"卡死。
    """
    try:
        limiter = anyio.to_thread.current_default_thread_limiter()
        if limiter.total_tokens < _ANYIO_POOL_TOKENS:
            old = limiter.total_tokens
            limiter.total_tokens = _ANYIO_POOL_TOKENS
            logger.info(
                "anyio threadpool tokens: %s -> %s (executor=%s)",
                old, _ANYIO_POOL_TOKENS, _EXECUTOR_WORKERS,
            )
    except Exception as e:
        logger.warning("tune anyio threadpool failed: %s", e)


def _run_with_timeout(fn, timeout: float):
    """把可能阻塞的同步调用丢线程跑，到点没回就给客户端返回 504。

    注意：Python 无法强制中断线程，超时只让本请求快速失败、释放 uvicorn worker；
    底层那个还在 socket 上 read 的线程会自然跑完后才结束（线程池会回收）。
    """
    fut = _executor.submit(fn)
    try:
        return fut.result(timeout=timeout)
    except FuturesTimeout as e:
        raise HTTPException(
            status_code=504, detail=f"upstream timeout after {timeout}s"
        ) from e


def _close_device(d: Any) -> None:
    """尽力关闭 Device 持有的 HTTP client；底层 adb-server 那条 TCP 不在本进程管。"""
    for attr in ("_http", "session", "_session", "http"):
        try:
            sess = getattr(d, attr, None)
            if sess is not None and hasattr(sess, "close"):
                sess.close()
        except Exception:
            pass


@contextmanager
def use_device(serial: str) -> Iterator[Any]:
    """请求级 Device，离开 with 块立刻释放，永不缓存。

    所有路由都应该用 ``with use_device(...) as d:``，避免出现僵尸会话。
    """
    serial = (serial or "").strip()
    if not serial:
        raise HTTPException(status_code=400, detail="serial required")

    try:
        d = _run_with_timeout(lambda: u2.connect(serial), timeout=CONNECT_TIMEOUT)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("u2.connect failed serial=%s err=%s", serial, e)
        raise HTTPException(
            status_code=502, detail=f"u2.connect failed: {e}"
        ) from e

    try:
        yield d
    finally:
        _close_device(d)


def _call(d: Any, fn, timeout: float | None = None) -> Any:
    """统一入口：所有真正打到设备的调用都套一层超时，避免单请求把 worker 卡死。"""
    return _run_with_timeout(fn, timeout=timeout if timeout is not None else CALL_TIMEOUT)


class ConnectBody(BaseModel):
    serial: str = Field(..., description="adb serial，如 emulator-5554 或 192.168.1.10:5555")


@app.post("/session/connect")
def session_connect(body: ConnectBody):
    """无状态接口：握一次手并返回设备 info，本进程不保留任何会话。"""
    with use_device(body.serial) as d:
        info = _call(d, lambda: d.info)
    return {"ok": True, "serial": body.serial, "info": info}


@app.post("/session/disconnect")
def session_disconnect(serial: str = Query(...)):
    """保留路由兼容客户端；当前实现无状态，故为 no-op。"""
    return {"ok": True}


class ClickBody(BaseModel):
    serial: str
    x: int
    y: int


@app.post("/click")
def click_xy(body: ClickBody):
    with use_device(body.serial) as d:
        _call(d, lambda: d.click(body.x, body.y))
    return {"ok": True}


class TextClickBody(BaseModel):
    serial: str
    text: str
    timeout: float = 10.0
    contains: bool = Field(
        True,
        description="精确未命中时是否回退到 textContains 包含匹配；False 则只做精确匹配",
    )
    debug: bool = Field(
        False,
        description=(
            "为 True 时在返回体里附带页面 text 列表（会额外触发 dump_hierarchy，"
            "可能让单次失败请求耗时增加 1~5s，注意上游 nginx/网关 proxy_read_timeout）"
        ),
    )


@app.post("/click_text")
def click_text(body: TextClickBody):
    """点击文本控件。

    与 /has_text、/wait_text 一致，一律返回 HTTP 200，业务结果通过返回体表达：
      成功： {"ok": true, "clicked": true, "matched_by": "text"|"textContains"}
      失败： {"ok": true, "clicked": false, "matched_by": "none", "message": "..."}
    """
    # 业务等待 + dump 都可能花较久，单独放宽这条路由的超时上限
    effective_timeout = max(CALL_TIMEOUT, body.timeout + 10.0)

    with use_device(body.serial) as d:
        def _do() -> dict[str, Any]:
            el = d(text=body.text)
            if el.wait(timeout=body.timeout):
                el.click()
                return {"ok": True, "clicked": True, "matched_by": "text"}

            if body.contains:
                el2 = d(textContains=body.text)
                if el2.exists:
                    el2.click()
                    return {"ok": True, "clicked": True, "matched_by": "textContains"}

            result: dict[str, Any] = {
                "ok": True,
                "clicked": False,
                "matched_by": "none",
                "message": f'no widget text="{body.text}"',
                "contains_tried": body.contains,
            }

            if body.debug:
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
                result["similar_or_visible_texts"] = similar

            return result

        return _call(d, _do, timeout=effective_timeout)


class ShellBody(BaseModel):
    serial: str
    command: str


@app.post("/shell")
def adb_shell(body: ShellBody):
    with use_device(body.serial) as d:
        out = _call(d, lambda: d.shell(body.command))
    return {"ok": True, "output": out}


_SCREENSHOT_TIMEOUT = max(CALL_TIMEOUT, 60.0)


def _screenshot_raw_png(d: Any) -> bytes:
    """直接从 atx-agent 拿原始 PNG 字节，绕过 PIL 的 decode/encode。

    优先用 uiautomator2 的 ``format="raw"`` 接口；不同版本签名差异较大，
    都拿不到时回退到 PIL 路径，至少能保证可用。
    """
    try:
        raw = d.screenshot(format="raw")
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
    except TypeError:
        # 老版本不支持 format 参数
        pass
    except Exception as e:
        logger.debug("screenshot(format=raw) failed, fallback to PIL: %s", e)

    im = d.screenshot()
    buf = io.BytesIO()
    try:
        im.save(buf, format="PNG")
        return buf.getvalue()
    finally:
        buf.close()
        if hasattr(im, "close"):
            try:
                im.close()
            except Exception:
                pass


def _screenshot_jpeg(d: Any, quality: int) -> bytes:
    """需要 JPEG 时才走一次 PIL，体积/速度都比 PNG 强一截。"""
    from PIL import Image  # noqa: PLC0415

    im = d.screenshot()
    try:
        rgb = im.convert("RGB") if im.mode != "RGB" else im
        buf = io.BytesIO()
        try:
            rgb.save(buf, format="JPEG", quality=quality, optimize=False)
            return buf.getvalue()
        finally:
            buf.close()
            if rgb is not im and hasattr(rgb, "close"):
                try:
                    rgb.close()
                except Exception:
                    pass
    finally:
        if hasattr(im, "close"):
            try:
                im.close()
            except Exception:
                pass


@app.get("/screenshot")
def screenshot(
    serial: str = Query(...),
    png: bool = Query(
        True,
        description="True=直接二进制；False=JSON+base64。fmt=jpeg 时输出会是 image/jpeg",
    ),
    fmt: str = Query("png", description="png 或 jpeg；jpeg 体积/CPU 都明显更省"),
    quality: int = Query(
        80, ge=10, le=100, description="JPEG 质量，仅 fmt=jpeg 时生效"
    ),
):
    """优化版截图：

    - ``fmt=png``：跳过 PIL，直接吐 atx-agent 原始 PNG 字节，省去无意义的解-编。
    - ``fmt=jpeg``：体积小约 8x、CPU 降一个量级，自动化识别一般 quality=70~85 够用。
    - ``png=false``：维持旧契约，返回 ``{ok, image_base64}``。
    """
    fmt = (fmt or "png").strip().lower()
    if fmt == "jpg":
        fmt = "jpeg"
    if fmt not in ("png", "jpeg"):
        raise HTTPException(400, detail="fmt must be png or jpeg")

    with use_device(serial) as d:
        if fmt == "png":
            data = _call(d, lambda: _screenshot_raw_png(d), timeout=_SCREENSHOT_TIMEOUT)
        else:
            data = _call(
                d, lambda: _screenshot_jpeg(d, quality), timeout=_SCREENSHOT_TIMEOUT
            )

    media_type = "image/png" if fmt == "png" else "image/jpeg"
    if png:
        return Response(content=data, media_type=media_type)
    return {
        "ok": True,
        "format": fmt,
        "size": len(data),
        "image_base64": base64.b64encode(data).decode("ascii"),
    }


@app.get("/dump")
def dump_hierarchy(serial: str = Query(...)):
    with use_device(serial) as d:
        xml = _call(d, lambda: d.dump_hierarchy())
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
    with use_device(body.serial) as d:
        _call(d, lambda: d.swipe(body.sx, body.sy, body.ex, body.ey, body.duration))
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
    with use_device(body.serial) as d:
        try:
            ok = bool(_call(d, lambda: d(**body.selector).exists))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, detail=f"bad selector: {e}") from e
    return {"ok": True, "exists": ok}


@app.post("/wait")
def selector_wait(body: SelectorBody):
    """按 u2 选择器等待元素出现，返回 found=true/false。"""
    effective_timeout = max(CALL_TIMEOUT, body.timeout + 10.0)
    with use_device(body.serial) as d:
        try:
            found = bool(
                _call(
                    d,
                    lambda: d(**body.selector).wait(timeout=body.timeout),
                    timeout=effective_timeout,
                )
            )
        except HTTPException:
            raise
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
    """当前界面是否包含给定文本（不等待）。"""
    with use_device(body.serial) as d:
        def _do() -> dict[str, Any]:
            if bool(d(text=body.text).exists):
                return {"ok": True, "exists": True, "matched_by": "text"}
            if body.contains and bool(d(textContains=body.text).exists):
                return {"ok": True, "exists": True, "matched_by": "textContains"}
            return {"ok": True, "exists": False, "matched_by": "none"}

        return _call(d, _do)


@app.post("/wait_text")
def wait_text(body: TextBody):
    """等待给定文本出现，返回 found=true/false。"""
    effective_timeout = max(CALL_TIMEOUT, body.timeout + 10.0)

    with use_device(body.serial) as d:
        def _do() -> dict[str, Any]:
            if bool(d(text=body.text).wait(timeout=body.timeout)):
                return {"ok": True, "found": True, "matched_by": "text"}
            if body.contains and bool(d(textContains=body.text).exists):
                return {"ok": True, "found": True, "matched_by": "textContains"}
            return {"ok": True, "found": False, "matched_by": "none"}

        return _call(d, _do, timeout=effective_timeout)


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

    所有动作均返回 HTTP 200，业务结果通过返回体的字段表达；
    只有「请求本身无效」（XPath 语法错误 / unknown action）才返回 400。
    """
    act = (body.action or "exists").strip().lower()
    if act not in ("exists", "wait", "click", "get_text", "info", "all"):
        raise HTTPException(400, detail=f"unknown action: {body.action}")

    effective_timeout = max(CALL_TIMEOUT, body.timeout + 10.0)

    with use_device(body.serial) as d:
        try:
            x = _call(d, lambda: d.xpath(body.xpath))
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, detail=f"bad xpath: {e}") from e

        if act == "exists":
            return {"ok": True, "exists": bool(_call(d, lambda: x.exists))}

        if act == "wait":
            return {
                "ok": True,
                "found": bool(
                    _call(d, lambda: x.wait(timeout=body.timeout), timeout=effective_timeout)
                ),
            }

        if act == "click":
            def _click() -> dict[str, Any]:
                if not x.wait(timeout=body.timeout):
                    return {
                        "ok": True,
                        "found": False,
                        "clicked": False,
                        "message": f"no node matched xpath: {body.xpath}",
                    }
                x.click()
                return {"ok": True, "found": True, "clicked": True}

            return _call(d, _click, timeout=effective_timeout)

        if act == "get_text":
            def _get_text() -> dict[str, Any]:
                if not x.wait(timeout=body.timeout):
                    return {
                        "ok": True,
                        "found": False,
                        "text": None,
                        "message": f"no node matched xpath: {body.xpath}",
                    }
                return {"ok": True, "found": True, "text": x.get_text()}

            return _call(d, _get_text, timeout=effective_timeout)

        if act == "info":
            def _info() -> dict[str, Any]:
                el = x.wait(timeout=body.timeout)
                if not el:
                    return {
                        "ok": True,
                        "found": False,
                        "info": None,
                        "message": f"no node matched xpath: {body.xpath}",
                    }
                info = getattr(el, "info", None)
                if info is None:
                    info = dict(getattr(el, "attrib", {}) or {})
                return {"ok": True, "found": True, "info": info}

            return _call(d, _info, timeout=effective_timeout)

        # all
        def _all() -> dict[str, Any]:
            nodes = x.all() or []
            items = []
            for n in nodes:
                info = getattr(n, "info", None)
                if info is None:
                    info = dict(getattr(n, "attrib", {}) or {})
                items.append(info)
            return {"ok": True, "count": len(items), "items": items}

        return _call(d, _all)


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
def push_file(
    serial: str = Form(..., description="adb serial"),
    dst: str = Form(..., description="设备端目标绝对路径"),
    mode: str = Form("0o644", description="权限：0o644 / 0x1A4 / 644 等"),
    file: UploadFile = File(..., description="要上传的文件"),
):
    """将上传文件 PUSH 到设备端 dst 路径。

    用 sync def：FastAPI 会把整个函数丢到 Starlette 线程池跑，
    避免在 event loop 里做阻塞 IO 卡住 uvicorn 全局调度。
    `file.file` 是底层的 ``SpooledTemporaryFile``，可以直接同步读。
    """
    data = file.file.read()
    perm = _parse_mode(mode)

    # 大文件 push 比普通调用慢得多，临时把超时放宽到 5 分钟
    push_timeout = max(CALL_TIMEOUT, 300.0)

    with use_device(serial) as d:
        try:
            _call(d, lambda: d.push(io.BytesIO(data), dst, mode=perm), timeout=push_timeout)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, detail=f"push failed: {e}") from e

    return {
        "ok": True,
        "dst": dst,
        "size": len(data),
        "mode": oct(perm),
        "filename": file.filename,
    }


@app.get("/pull")
def pull_file(
    serial: str = Query(..., description="adb serial"),
    src: str = Query(..., description="设备端要拉取的文件绝对路径"),
):
    """从设备端把 src 文件拉到调用方（与 /push 相反方向）。

    底层用 ``uiautomator2.Device.pull`` 走 atx-agent 的下载通道；先落到本机临时文件，
    读出字节后立即删除临时文件，再以二进制流返回。大文件拉取较慢，超时放宽到 5 分钟。
    """
    import tempfile

    pull_timeout = max(CALL_TIMEOUT, 300.0)

    with use_device(serial) as d:
        def _do() -> bytes:
            fd, tmp = tempfile.mkstemp(prefix="u2pull_")
            os.close(fd)
            try:
                d.pull(src, tmp)
                with open(tmp, "rb") as f:
                    return f.read()
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass

        try:
            data = _call(d, _do, timeout=pull_timeout)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(502, detail=f"pull failed: {e}") from e

    filename = os.path.basename(src) or "pulled.bin"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Pulled-Size": str(len(data)),
        },
    )


@app.get("/health")
def health():
    """无状态版本：只表明服务自身存活，不再列出会话列表。"""
    return {"ok": True, "stateless": True}
