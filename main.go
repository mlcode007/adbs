package main

import (
	"adbs/api"
)

func main() {
	maybeStartU2Bridge()
	// 启动API（:8081；若未设置 U2_DISABLE，则 /u2 反向代理至 python_u2_bridge）
	api.Init()
}
