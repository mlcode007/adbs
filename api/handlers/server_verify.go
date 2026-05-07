package handlers

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

func u2BackendForProbe() string {
	if v := os.Getenv("U2_BACKEND"); v != "" {
		return v
	}
	port := os.Getenv("U2_INTERNAL_PORT")
	if port == "" {
		port = "18082"
	}
	return "http://127.0.0.1:" + port
}

func listenPortProbe() int {
	p := os.Getenv("ADBS_PORT")
	if p == "" {
		return 18081
	}
	n, err := strconv.Atoi(p)
	if err != nil || n < 1 || n > 65535 {
		return 18081
	}
	return n
}

// GetServerVerify GET /api/server/verify — 服务器侧自检（ADB、U2 后端等）。
func GetServerVerify(c *gin.Context) {
	out := gin.H{
		"server_time":  time.Now().Format(time.RFC3339),
		"go_version":   runtime.Version(),
		"listen_port":  listenPortProbe(),
		"u2_disabled":  os.Getenv("U2_DISABLE") != "",
		"adb_server":   probeADBTCP(),
		"adb_cli":      probeADBCLI(),
		"u2_backend":   probeHTTP(u2BackendForProbe(), 2*time.Second),
		"goproxy":      os.Getenv("GOPROXY"),
	}
	if h, err := os.Hostname(); err == nil {
		out["hostname"] = h
	}
	c.JSON(http.StatusOK, out)
}

func probeADBTCP() gin.H {
	addr := "127.0.0.1:5037"
	conn, err := net.DialTimeout("tcp", addr, 1500*time.Millisecond)
	if err != nil {
		return gin.H{"ok": false, "detail": fmt.Sprintf("无法连接 %s: %v", addr, err)}
	}
	_ = conn.Close()
	return gin.H{"ok": true, "detail": addr + " 可达"}
}

func probeADBCLI() gin.H {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "adb", "version")
	out, err := cmd.CombinedOutput()
	s := strings.TrimSpace(string(out))
	if err != nil {
		if s == "" {
			s = err.Error()
		}
		return gin.H{"ok": false, "detail": s}
	}
	if len(s) > 200 {
		s = s[:200] + "…"
	}
	return gin.H{"ok": true, "detail": s}
}

func probeHTTP(base string, timeout time.Duration) gin.H {
	if os.Getenv("U2_DISABLE") != "" {
		return gin.H{"ok": true, "detail": "已设置 U2_DISABLE，跳过探测"}
	}
	u := strings.TrimRight(base, "/") + "/"
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return gin.H{"ok": false, "detail": err.Error()}
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return gin.H{"ok": false, "detail": err.Error()}
	}
	_ = resp.Body.Close()
	return gin.H{"ok": resp.StatusCode < 500, "detail": fmt.Sprintf("%s → HTTP %d", u, resp.StatusCode)}
}
