#!/usr/bin/env python3
"""
通过 uiautomator2 HTTP 桥（/u2）按坐标远程点击手机。
仅需 Python 标准库；桥服务端见 adbs/python_u2_bridge/app.py。

环境变量（可选）：
  U2_BASE       例如 https://主机/u2 或 http://127.0.0.1:18081/u2
  ADEVICE_SERIAL  adb 序列号，如 192.168.1.5:5555

示例：
  export U2_BASE='http://127.0.0.1:18081/u2'
  export ADEVICE_SERIAL=emulator-5554
  python3 u2_remote_tap.py 540 1200

  python3 u2_remote_tap.py -k 100 200 --serial 10.0.0.5:5555

HTTPS 校验失败时可加 -k（或 export U2_INSECURE_SSL=1）。
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request


def _ssl_ctx(insecure: bool) -> ssl.SSLContext | None:
    return ssl._create_unverified_context() if insecure else None


def _post(url: str, body: dict, *, insecure: bool, timeout: float = 60.0) -> None:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    ctx = _ssl_ctx(insecure)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        resp.read()


def main() -> int:
    env_base = os.environ.get("U2_BASE", "").strip()
    env_serial = os.environ.get("ADEVICE_SERIAL", "").strip()
    env_skip = os.environ.get("U2_INSECURE_SSL", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )

    p = argparse.ArgumentParser(description="远程坐标点击（u2 HTTP 桥）")
    p.add_argument("x", type=int, help="像素 x")
    p.add_argument("y", type=int, help="像素 y")
    p.add_argument(
        "--base",
        default=env_base or "http://127.0.0.1:18081/u2",
        help="桥前缀 URL（末尾不要多余路径）",
    )
    p.add_argument("--serial", "-s", default=env_serial, help="adb serial")
    p.add_argument(
        "-k",
        "--insecure",
        action="store_true",
        help="跳过 HTTPS 证书校验",
    )
    args = p.parse_args()
    insecure = args.insecure or env_skip
    base = args.base.rstrip("/")
    serial = args.serial.strip()
    if not serial:
        print("请设置 --serial 或环境变量 ADEVICE_SERIAL", file=sys.stderr)
        return 2

    url = f"{base}/click"
    try:
        _post(url, {"serial": serial, "x": args.x, "y": args.y}, insecure=insecure)
    except urllib.error.HTTPError as e:
        print(e.read().decode(errors="replace"), file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(str(e.reason), file=sys.stderr)
        return 1

    print(f"ok tap ({args.x}, {args.y}) serial={serial}")
    return 0


if __name__ == "__main__":
    """
    export U2_BASE='https://caiji-adb-console-itoamms.smzdm.com/u2'
    export ADEVICE_SERIAL=10.131.14.15
    python3 u2_remote_tap.py -k 540 1200
    """
    raise SystemExit(main())
