package main

import (
	"adbs/api"
)

func main() {
	maybeStartU2Bridge()
	// 启动API（默认 :18081）；/u2→python_u2_bridge；控制台 SPA 静态→/u5/*（本进程）；附加服务→/u5-bridge→127.0.0.1:18085
	api.Init()
}
