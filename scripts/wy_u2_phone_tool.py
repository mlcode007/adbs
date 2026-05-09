#!/usr/bin/env python3
"""
通用手机自动化脚本：支持两种后端。

【后端一：HTTP 桥】与 adbs 同部署的 python_u2_bridge（Go 反代到 /u2），覆盖服务端全部接口：
  session/connect、session/disconnect、click、click_text、swipe、shell、screenshot、dump、health

【后端二：本地 uiautomator2】本机已 adb 连接设备且 pip 安装 uiautomator2 时使用，可额外执行：
  press、keyevent、app-start、input、long-tap、double-tap、wait-text、info 等常用封装。
  完整 Python API 见文末「uiautomator2 常用 API」。

示例（远程桥，与公司 screenshot_automation.py 一致的环境变量）：
  export U2_BASE='http://127.0.0.1:18081/u2'
  export ADEVICE_SERIAL=emulator-5554
  python3 u2_phone_tool.py health
  python3 u2_phone_tool.py connect
  python3 u2_phone_tool.py tap 540 1200
  python3 u2_phone_tool.py tap-text 设置
  python3 u2_phone_tool.py swipe 300 800 300 300
  python3 u2_phone_tool.py shell "echo hello"
  python3 u2_phone_tool.py screenshot -o cap.png
  python3 u2_phone_tool.py dump -o ui.xml

示例（本机直连，无需桥）：
  python3 u2_phone_tool.py --backend local --serial emulator-5554 info
  python3 u2_phone_tool.py --backend local tap-text 设置
  python3 u2_phone_tool.py --backend local press back
  python3 u2_phone_tool.py --backend local app-start com.android.settings

HTTPS 证书问题：export U2_INSECURE_SSL=1 或加 --insecure

----------
uiautomator2 常用 API（本地交互式脚本或 --backend local 扩展时可查阅）

连接与会话：
  u2.connect(serial)           # USB / 无线 adb 后的序列号
  d.info                       # 分辨率、旋转等
  d.serial                     # 序列号

全局手势与按键：
  d.click(x, y) | d.double_click(x, y) | d.long_click(x, y)
  d.swipe(sx, sy, ex, ey, duration=0.5)
  d.drag(sx, sy, ex, ey, duration=0.5)
  d.press("home"|"back"|"recent"|"power"|"menu"|"volume_up"|"volume_down")
  d.shell(cmd)                 # 执行 adb shell 命令字符串

界面元素（UiObject，链式）：
  d(text="文案") | d(textContains="部分") | d(resourceId="包名:id/xxx")
  d(description="…") | d(className="android.widget.Button")
  el = d(text="确定"); el.exists | el.get_text() | el.click() | el.wait(timeout=10)
  d.xpath("//android.widget.TextView[@text='…']").click()

应用：
  d.app_current()              # 当前前台包名/Activity
  d.app_start(package, activity?) | d.app_stop(package)
  d(watcher=…)                 # 自动化监听弹窗等（高级）

截图与层次：
  im = d.screenshot(); im.save("a.png")
  xml = d.dump_hierarchy()

输入（部分机型需开启「USB 调试（安全设置）」等）：
  d.set_input_ime(True)        # 启用 FastInputIME（若使用 send_keys）
  d.send_keys("文本")          # 依赖输入法插件

更多见官方文档与 IDE 对 uiautomator2.Device 的补全。
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _ssl_insecure_enabled(cli_insecure: bool) -> bool:
    if cli_insecure:
        return True
    v = os.environ.get("U2_INSECURE_SSL", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _ssl_context(insecure: bool) -> ssl.SSLContext | None:
    if insecure:
        return ssl._create_unverified_context()
    return None


def _post_json(
    url: str,
    payload: dict[str, Any] | None,
    timeout: float = 120.0,
    *,
    ssl_context: ssl.SSLContext | None = None,
) -> dict[str, Any]:
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
        body = resp.read().decode("utf-8")
        if not body:
            return {}
        return json.loads(body)


def _get_bytes(
    url: str,
    timeout: float = 120.0,
    *,
    ssl_context: ssl.SSLContext | None = None,
) -> bytes:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
        return resp.read()


def _get_json(
    url: str,
    timeout: float = 30.0,
    *,
    ssl_context: ssl.SSLContext | None = None,
) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
        body = resp.read().decode("utf-8")
        if not body:
            return {}
        return json.loads(body)


def _http_connect(base: str, serial: str, ssl_ctx: ssl.SSLContext | None) -> dict[str, Any]:
    return _post_json(f"{base}/session/connect", {"serial": serial}, ssl_context=ssl_ctx)


def _http_disconnect(base: str, serial: str, ssl_ctx: ssl.SSLContext | None) -> dict[str, Any]:
    q = urllib.parse.quote(serial, safe="")
    return _post_json(
        f"{base}/session/disconnect?serial={q}",
        {},
        ssl_context=ssl_ctx,
    )


def _require_serial(serial: str) -> str:
    s = serial.strip()
    if not s:
        print("请指定 --serial 或设置环境变量 ADEVICE_SERIAL", file=sys.stderr)
        sys.exit(2)
    return s


def _load_u2():
    try:
        import uiautomator2 as u2  # noqa: PLC0415
    except ImportError as e:
        print(
            "未安装 uiautomator2。请执行: pip install uiautomator2>=3.0.0",
            file=sys.stderr,
        )
        raise SystemExit(2) from e
    return u2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="通用 uiautomator2 手机操作（HTTP 桥 / 本地直连）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="详见脚本顶部文档字符串。",
    )
    parser.add_argument(
        "--backend",
        choices=("http", "local"),
        default="http",
        help="http=走 U2_BASE 桥（默认）；local=本机 pip 安装 uiautomator2 直连手机",
    )
    parser.add_argument(
        "--base",
        default=os.environ.get("U2_BASE", "https://caiji-adb-console-itoamms.smzdm.com/u2"),
        help="仅 http：桥前缀（环境变量 U2_BASE）",
    )
    parser.add_argument(
        "--insecure",
        "-k",
        action="store_true",
        help="仅 http：跳过 HTTPS 校验（或 U2_INSECURE_SSL=1）",
    )
    parser.add_argument(
        "--serial",
        default=os.environ.get("ADEVICE_SERIAL", ""),
        help="adb serial（环境变量 ADEVICE_SERIAL）",
    )

    sub = parser.add_subparsers(dest="cmd", required=True)

    p_health = sub.add_parser("health", help="检查桥是否可用（仅 http）")
    p_health.set_defaults(_handler=cmd_health)

    p_connect = sub.add_parser("connect", help="建立会话并打印设备 info")
    p_connect.set_defaults(_handler=cmd_connect)

    p_disconnect = sub.add_parser("disconnect", help="断开服务器侧会话缓存")
    p_disconnect.set_defaults(_handler=cmd_disconnect)

    p_tap = sub.add_parser("tap", aliases=("click",), help="点击坐标")
    p_tap.add_argument("x", type=int)
    p_tap.add_argument("y", type=int)
    p_tap.set_defaults(_handler=cmd_tap)

    p_tt = sub.add_parser("tap-text", aliases=("click-text",), help="按可见文案点击控件")
    p_tt.add_argument("text", help='元素 text 精确匹配，如 "设置"')
    p_tt.add_argument("--timeout", type=float, default=10.0)
    p_tt.set_defaults(_handler=cmd_tap_text)

    p_sw = sub.add_parser("swipe", help="滑动")
    p_sw.add_argument("sx", type=int)
    p_sw.add_argument("sy", type=int)
    p_sw.add_argument("ex", type=int)
    p_sw.add_argument("ey", type=int)
    p_sw.add_argument("--duration", type=float, default=0.5)
    p_sw.set_defaults(_handler=cmd_swipe)

    p_sh = sub.add_parser("shell", help="执行 adb shell 单行命令")
    p_sh.add_argument("command", help="传给 d.shell 的完整字符串")
    p_sh.set_defaults(_handler=cmd_shell)

    p_cap = sub.add_parser("screenshot", help="整屏截图 PNG")
    p_cap.add_argument("-o", "--output", default="screenshot.png")
    p_cap.add_argument("--tap-x", type=int, default=None)
    p_cap.add_argument("--tap-y", type=int, default=None)
    p_cap.add_argument("--delay", type=float, default=1.0, help="连接后等待秒数（仅 http 常用）")
    p_cap.set_defaults(_handler=cmd_screenshot)

    p_dump = sub.add_parser("dump", help="导出当前界面 UI 层次 XML")
    p_dump.add_argument("-o", "--output", default="window_dump.xml")
    p_dump.set_defaults(_handler=cmd_dump)

    # --- local-only ---
    p_info = sub.add_parser("info", help="打印 d.info（建议 --backend local）")
    p_info.set_defaults(_handler=cmd_info)

    p_press = sub.add_parser("press", help="按键：home back recent power menu volume_up volume_down（建议 local）")
    p_press.add_argument(
        "key",
        help="uiautomator2 d.press 支持的键名",
    )
    p_press.set_defaults(_handler=cmd_press)

    p_keyevent = sub.add_parser("keyevent", help="发送 keyevent 数字码（local：d.shell input keyevent）")
    p_keyevent.add_argument("code", type=int)
    p_keyevent.set_defaults(_handler=cmd_keyevent)

    p_app = sub.add_parser("app-start", help="启动应用（local）")
    p_app.add_argument("package")
    p_app.add_argument("activity", nargs="?", default=None)
    p_app.set_defaults(_handler=cmd_app_start)

    p_in = sub.add_parser("input", help="输入文本（local：send_keys，需合适输入法环境）")
    p_in.add_argument("text")
    p_in.set_defaults(_handler=cmd_input)

    p_lt = sub.add_parser("long-tap", help="长按坐标（local）")
    p_lt.add_argument("x", type=int)
    p_lt.add_argument("y", type=int)
    p_lt.add_argument("--duration", type=float, default=1.0)
    p_lt.set_defaults(_handler=cmd_long_tap)

    p_dt = sub.add_parser("double-tap", help="双击坐标（local）")
    p_dt.add_argument("x", type=int)
    p_dt.add_argument("y", type=int)
    p_dt.set_defaults(_handler=cmd_double_tap)

    p_wt = sub.add_parser("wait-text", help="等待文案出现（local）")
    p_wt.add_argument("text")
    p_wt.add_argument("--timeout", type=float, default=10.0)
    p_wt.set_defaults(_handler=cmd_wait_text)

    args = parser.parse_args()
    backend = args.backend
    base = args.base.rstrip("/")
    insecure = _ssl_insecure_enabled(args.insecure)
    ssl_ctx = _ssl_context(insecure)

    handler = getattr(args, "_handler", None)
    if handler is None:
        parser.print_help()
        return 2

    # health 仅 http 有意义；local 下转为打印本机提示
    if args.cmd == "health" and backend == "local":
        print("health 仅用于 HTTP 桥；本地模式请用: adb devices 与 python3 -c \"import uiautomator2 as u2; print(u2.connect('SERIAL').info)\"")
        return 0

    return int(handler(args, base, ssl_ctx))


def cmd_health(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    try:
        r = _get_json(f"{base}/health", ssl_context=ssl_ctx)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"无法访问 {base}: {e.reason}", file=sys.stderr)
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


def cmd_connect(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    serial = _require_serial(args.serial)
    if args.backend == "local":
        u2 = _load_u2()
        d = u2.connect(serial)
        print(json.dumps({"ok": True, "serial": serial, "info": d.info}, ensure_ascii=False, indent=2))
        return 0
    try:
        r = _http_connect(base, serial, ssl_ctx)
    except urllib.error.HTTPError as e:
        print(f"连接失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"请求失败: {e.reason}", file=sys.stderr)
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


def cmd_disconnect(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    serial = _require_serial(args.serial)
    if args.backend == "local":
        print("disconnect 仅释放服务端桥缓存；本地模式无需调用。", file=sys.stderr)
        return 0
    try:
        r = _http_disconnect(base, serial, ssl_ctx)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"请求失败: {e.reason}", file=sys.stderr)
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


def cmd_tap(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    serial = _require_serial(args.serial)
    if args.backend == "local":
        u2 = _load_u2()
        u2.connect(serial).click(args.x, args.y)
        print(json.dumps({"ok": True}, ensure_ascii=False))
        return 0
    try:
        _http_connect(base, serial, ssl_ctx)
        r = _post_json(
            f"{base}/click",
            {"serial": serial, "x": args.x, "y": args.y},
            ssl_context=ssl_ctx,
        )
    except urllib.error.HTTPError as e:
        print(f"点击失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"请求失败: {e.reason}", file=sys.stderr)
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


def cmd_tap_text(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    serial = _require_serial(args.serial)
    if args.backend == "local":
        u2 = _load_u2()
        d = u2.connect(serial)
        el = d(text=args.text)
        if not el.wait(timeout=args.timeout):
            print(f'未找到 text="{args.text}"', file=sys.stderr)
            return 1
        el.click()
        print(json.dumps({"ok": True}, ensure_ascii=False))
        return 0
    try:
        _http_connect(base, serial, ssl_ctx)
        r = _post_json(
            f"{base}/click_text",
            {"serial": serial, "text": args.text, "timeout": args.timeout},
            ssl_context=ssl_ctx,
        )
    except urllib.error.HTTPError as e:
        print(f"失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"请求失败: {e.reason}", file=sys.stderr)
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


def cmd_swipe(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    serial = _require_serial(args.serial)
    if args.backend == "local":
        u2 = _load_u2()
        u2.connect(serial).swipe(args.sx, args.sy, args.ex, args.ey, args.duration)
        print(json.dumps({"ok": True}, ensure_ascii=False))
        return 0
    try:
        _http_connect(base, serial, ssl_ctx)
        r = _post_json(
            f"{base}/swipe",
            {
                "serial": serial,
                "sx": args.sx,
                "sy": args.sy,
                "ex": args.ex,
                "ey": args.ey,
                "duration": args.duration,
            },
            ssl_context=ssl_ctx,
        )
    except urllib.error.HTTPError as e:
        print(f"失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"请求失败: {e.reason}", file=sys.stderr)
        return 1
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0


def cmd_shell(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    serial = _require_serial(args.serial)
    if args.backend == "local":
        u2 = _load_u2()
        out = u2.connect(serial).shell(args.command)
        print(out, end="" if str(out).endswith("\n") else "\n")
        return 0
    try:
        _http_connect(base, serial, ssl_ctx)
        r = _post_json(
            f"{base}/shell",
            {"serial": serial, "command": args.command},
            ssl_context=ssl_ctx,
        )
    except urllib.error.HTTPError as e:
        print(f"失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"请求失败: {e.reason}", file=sys.stderr)
        return 1
    out = r.get("output", "")
    print(out, end="" if str(out).endswith("\n") else "\n")
    return 0


def cmd_screenshot(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    serial = _require_serial(args.serial)
    if args.backend == "local":
        u2 = _load_u2()
        d = u2.connect(serial)
        if args.tap_x is not None and args.tap_y is not None:
            d.click(args.tap_x, args.tap_y)
            time.sleep(0.5)
        im = d.screenshot()
        path = os.path.abspath(args.output)
        im.save(path)
        print(f"已保存: {path}")
        return 0
    try:
        _http_connect(base, serial, ssl_ctx)
    except urllib.error.HTTPError as e:
        print(f"连接失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"请求失败: {e.reason}", file=sys.stderr)
        return 1
    time.sleep(max(0.0, args.delay))
    if args.tap_x is not None and args.tap_y is not None:
        try:
            _post_json(
                f"{base}/click",
                {"serial": serial, "x": args.tap_x, "y": args.tap_y},
                ssl_context=ssl_ctx,
            )
        except urllib.error.HTTPError as e:
            print(f"点击失败: HTTP {e.code}", file=sys.stderr)
            return 1
        time.sleep(0.5)
    try:
        png = _get_bytes(
            f"{base}/screenshot?serial={urllib.parse.quote(serial, safe='')}&png=1",
            ssl_context=ssl_ctx,
        )
    except urllib.error.HTTPError as e:
        print(f"截图失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"截图请求失败: {e.reason}", file=sys.stderr)
        return 1
    path = os.path.abspath(args.output)
    with open(path, "wb") as f:
        f.write(png)
    print(f"已保存: {path} ({len(png)} bytes)")
    return 0


def cmd_dump(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    serial = _require_serial(args.serial)
    if args.backend == "local":
        u2 = _load_u2()
        xml = u2.connect(serial).dump_hierarchy()
        path = os.path.abspath(args.output)
        with open(path, "w", encoding="utf-8") as f:
            f.write(xml)
        print(f"已保存: {path}")
        return 0
    try:
        _http_connect(base, serial, ssl_ctx)
        data = _get_bytes(
            f"{base}/dump?serial={urllib.parse.quote(serial, safe='')}",
            ssl_context=ssl_ctx,
        )
    except urllib.error.HTTPError as e:
        print(f"dump 失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"请求失败: {e.reason}", file=sys.stderr)
        return 1
    path = os.path.abspath(args.output)
    with open(path, "wb") as f:
        f.write(data)
    print(f"已保存: {path} ({len(data)} bytes)")
    return 0


def cmd_info(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    serial = _require_serial(args.serial)
    if args.backend == "http":
        try:
            r = _http_connect(base, serial, ssl_ctx)
        except urllib.error.HTTPError as e:
            print(f"失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
            return 1
        except urllib.error.URLError as e:
            print(f"请求失败: {e.reason}", file=sys.stderr)
            return 1
        info = r.get("info", r)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    u2 = _load_u2()
    print(json.dumps(u2.connect(serial).info, ensure_ascii=False, indent=2))
    return 0


def cmd_press(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    if args.backend != "local":
        print("press 需要 --backend local（HTTP 桥未暴露该接口）", file=sys.stderr)
        return 2
    serial = _require_serial(args.serial)
    u2 = _load_u2()
    u2.connect(serial).press(args.key)
    print(json.dumps({"ok": True, "key": args.key}, ensure_ascii=False))
    return 0


def cmd_keyevent(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    if args.backend != "local":
        print("keyevent 需要 --backend local", file=sys.stderr)
        return 2
    serial = _require_serial(args.serial)
    u2 = _load_u2()
    u2.connect(serial).shell(f"input keyevent {args.code}")
    print(json.dumps({"ok": True, "code": args.code}, ensure_ascii=False))
    return 0


def cmd_app_start(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    if args.backend != "local":
        print("app-start 需要 --backend local", file=sys.stderr)
        return 2
    serial = _require_serial(args.serial)
    u2 = _load_u2()
    d = u2.connect(serial)
    if args.activity:
        d.app_start(args.package, args.activity)
    else:
        d.app_start(args.package)
    print(json.dumps({"ok": True, "package": args.package}, ensure_ascii=False))
    return 0


def cmd_input(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    if args.backend != "local":
        print("input 需要 --backend local", file=sys.stderr)
        return 2
    serial = _require_serial(args.serial)
    u2 = _load_u2()
    d = u2.connect(serial)
    if hasattr(d, "set_input_ime"):
        try:
            d.set_input_ime(True)
        except Exception:
            pass
    d.send_keys(args.text)
    print(json.dumps({"ok": True}, ensure_ascii=False))
    return 0


def cmd_long_tap(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    if args.backend != "local":
        print("long-tap 需要 --backend local", file=sys.stderr)
        return 2
    serial = _require_serial(args.serial)
    u2 = _load_u2()
    d = u2.connect(serial)
    try:
        d.long_click(args.x, args.y, duration=args.duration)
    except TypeError:
        d.long_click(args.x, args.y)
    print(json.dumps({"ok": True}, ensure_ascii=False))
    return 0


def cmd_double_tap(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    if args.backend != "local":
        print("double-tap 需要 --backend local", file=sys.stderr)
        return 2
    serial = _require_serial(args.serial)
    u2 = _load_u2()
    d = u2.connect(serial)
    if hasattr(d, "double_click"):
        d.double_click(args.x, args.y)
    else:
        d.click(args.x, args.y)
        time.sleep(0.05)
        d.click(args.x, args.y)
    print(json.dumps({"ok": True}, ensure_ascii=False))
    return 0


def cmd_wait_text(args: argparse.Namespace, base: str, ssl_ctx: ssl.SSLContext | None) -> int:
    if args.backend != "local":
        print("wait-text 需要 --backend local", file=sys.stderr)
        return 2
    serial = _require_serial(args.serial)
    u2 = _load_u2()
    el = u2.connect(serial)(text=args.text)
    if not el.wait(timeout=args.timeout):
        print(f'超时：未出现 text="{args.text}"', file=sys.stderr)
        return 1
    print(json.dumps({"ok": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
