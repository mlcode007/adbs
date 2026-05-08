#!/usr/bin/env python3
"""
通过 u2 bridge（Go 默认 :18081 下的 /u2）连接设备，可选点击坐标后保存整屏截图。

使用前：
  - 已启动 adbs，且能访问 http://127.0.0.1:18081/u2/health
  - adb devices 中已有目标机（USB 或 adb connect）

示例：
  python3 screenshot_automation.py --serial emulator-5554 -o out.png
  python3 screenshot_automation.py --serial 192.168.1.5:5555 --tap-x 540 --tap-y 1200 -o cap.png
  export ADEVICE_SERIAL=emulator-5554 && python3 screenshot_automation.py -o cap.png

HTTPS 若报 SSL 证书错误（常见于 Nginx 未配 fullchain）：
  - 根治：服务端 ssl_certificate 使用完整证书链（含中间证书）。
  - 临时：export U2_INSECURE_SSL=1  或  python3 ... --insecure

eg:
    export U2_BASE='https://caiji-adb-console-itoamms.smzdm.com/u2'
    python3 screenshot_automation.py --serial 10.131.12.39:5555 --insecure
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
    payload: dict,
    timeout: float = 60.0,
    *,
    ssl_context: ssl.SSLContext | None = None,
) -> dict:
    data = json.dumps(payload).encode("utf-8")
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
    timeout: float = 60.0,
    *,
    ssl_context: ssl.SSLContext | None = None,
) -> bytes:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
        return resp.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="u2 bridge：连接设备并保存截图")
    parser.add_argument(
        "--base",
        default=os.environ.get("U2_BASE", "https://caiji-adb-console-itoamms.smzdm.com/u2"),
        help="u2 前缀地址（可用环境变量 U2_BASE；线上 HTTPS 见文档说明）",
    )
    parser.add_argument(
        "--insecure",
        "-k",
        action="store_true",
        help="不校验 HTTPS 证书；也可用环境变量 U2_INSECURE_SSL=1（根因应修 Nginx fullchain）",
    )
    parser.add_argument(
        "--serial",
        default=os.environ.get("ADEVICE_SERIAL", ""),
        help="adb serial（也可用环境变量 ADEVICE_SERIAL）",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="screenshot.png",
        help="截图保存路径（默认 screenshot.png）",
    )
    parser.add_argument(
        "--tap-x",
        type=int,
        default=None,
        help="截图前点击坐标 x（与 --tap-y 同时指定才生效）",
    )
    parser.add_argument(
        "--tap-y",
        type=int,
        default=None,
        help="截图前点击坐标 y",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="连接成功后等待秒数，再执行点击/截图（默认 1）",
    )
    args = parser.parse_args()

    base = args.base.rstrip("/")
    serial = args.serial.strip()
    if not serial:
        print("请指定 --serial 或设置环境变量 ADEVICE_SERIAL", file=sys.stderr)
        return 2
    insecure = _ssl_insecure_enabled(args.insecure)
    ssl_ctx = _ssl_context(insecure)
    try:
        _post_json(
            f"{base}/session/connect",
            {"serial": serial},
            ssl_context=ssl_ctx,
        )
    except urllib.error.HTTPError as e:
        print(f"连接失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"无法访问 u2 bridge（{base}）: {e.reason}", file=sys.stderr)
        err_s = str(e.reason)
        if "CERTIFICATE_VERIFY_FAILED" in err_s or "certificate verify failed" in err_s.lower():
            print(
                "提示: 多为服务端未返回完整证书链。临时跳过校验可执行: export U2_INSECURE_SSL=1",
                file=sys.stderr,
            )
            print("     或加参数 --insecure ；根治请在 Nginx 使用 fullchain 作为 ssl_certificate。", file=sys.stderr)
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
            print(f"点击失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
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
        err_s = str(e.reason)
        if "CERTIFICATE_VERIFY_FAILED" in err_s or "certificate verify failed" in err_s.lower():
            print("提示: export U2_INSECURE_SSL=1 或 --insecure", file=sys.stderr)
        return 1

    out = os.path.abspath(args.output)
    with open(out, "wb") as f:
        f.write(png)

    print(f"已保存: {out} ({len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
