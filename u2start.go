package main

import (
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

// 设置 U2_AUTO_START=1 时，在启动 Go 服务前拉起 python_u2_bridge（监听 127.0.0.1:U2_INTERNAL_PORT，默认 18082）。
// 对外仍只访问 http://<host>:8081/u2/... ，无需再暴露第二端口。
func maybeStartU2Bridge() {
	if os.Getenv("U2_AUTO_START") != "1" {
		return
	}
	if os.Getenv("U2_DISABLE") != "" {
		return
	}

	wd, err := os.Getwd()
	if err != nil {
		log.Printf("u2 auto-start: getwd: %v", err)
		return
	}
	bridgeDir := filepath.Join(wd, "python_u2_bridge")
	if _, err := os.Stat(filepath.Join(bridgeDir, "app.py")); err != nil {
		log.Printf("u2 auto-start: skip (no %s/app.py)", bridgeDir)
		return
	}

	port := os.Getenv("U2_INTERNAL_PORT")
	if port == "" {
		port = "18082"
	}

	cmd := exec.Command("python3", "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", port)
	cmd.Dir = bridgeDir
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	if err := cmd.Start(); err != nil {
		log.Printf("u2 auto-start: %v", err)
		return
	}
	log.Printf("u2 bridge started pid=%d on 127.0.0.1:%s — use http://<host>:8081/u2/", cmd.Process.Pid, port)
	go func() { _ = cmd.Wait() }()

	time.Sleep(400 * time.Millisecond)
}
