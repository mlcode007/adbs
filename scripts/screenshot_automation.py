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
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def _post_json(url: str, payload: dict, timeout: float = 60.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        if not body:
            return {}
        return json.loads(body)


def _get_bytes(url: str, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="u2 bridge：连接设备并保存截图")
    parser.add_argument(
        "--base",
        default=os.environ.get("U2_BASE", "http://127.0.0.1:18081/u2"),
        help="u2 前缀地址（默认 http://127.0.0.1:18081/u2）",
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
    try:
        _post_json(f"{base}/session/connect", {"serial": serial})
    except urllib.error.HTTPError as e:
        print(f"连接失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"无法访问 u2 bridge（{base}）: {e.reason}", file=sys.stderr)
        return 1

    time.sleep(max(0.0, args.delay))

    if args.tap_x is not None and args.tap_y is not None:
        try:
            _post_json(
                f"{base}/click",
                {"serial": serial, "x": args.tap_x, "y": args.tap_y},
            )
        except urllib.error.HTTPError as e:
            print(f"点击失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
            return 1
        time.sleep(0.5)

    try:
        png = _get_bytes(
            f"{base}/screenshot?serial={urllib.parse.quote(serial, safe='')}&png=1"
        )
    except urllib.error.HTTPError as e:
        print(f"截图失败: HTTP {e.code} {e.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f"截图请求失败: {e.reason}", file=sys.stderr)
        return 1

    out = os.path.abspath(args.output)
    with open(out, "wb") as f:
        f.write(png)

    print(f"已保存: {out} ({len(png)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
