package main

import (
	"adbs/api"
)

func main() {
	maybeStartU2Bridge()
	// 启动API（默认 :18081，环境变量 ADBS_PORT 可改；若未设置 U2_DISABLE，则 /u2 反向代理至 python_u2_bridge；/u5 默认反代至 127.0.0.1:18085）
	api.Init()
}
