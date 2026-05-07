package router

import (
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
)

// u2BackendURL 为 python_u2_bridge（uvicorn）监听地址，仅本机回环，由 Go 在 ADBS_PORT（默认 18081）上以 /u2 对外转发。
// 环境变量：
//   U2_BACKEND     完整 URL，如 http://127.0.0.1:18082（优先级最高）
//   U2_INTERNAL_PORT  未设置 U2_BACKEND 时使用，默认 18082
func u2BackendURL() string {
	if v := os.Getenv("U2_BACKEND"); v != "" {
		return v
	}
	port := os.Getenv("U2_INTERNAL_PORT")
	if port == "" {
		port = "18082"
	}
	return "http://127.0.0.1:" + port
}

func u2ProxyHandler() gin.HandlerFunc {
	target, err := url.Parse(u2BackendURL())
	if err != nil {
		return func(c *gin.Context) {
			c.JSON(http.StatusServiceUnavailable, gin.H{"message": "invalid U2_BACKEND"})
		}
	}

	proxy := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL.Scheme = target.Scheme
			req.URL.Host = target.Host
			req.Host = target.Host

			p := strings.TrimPrefix(req.URL.Path, "/u2")
			if p == "" {
				p = "/"
			}
			if !strings.HasPrefix(p, "/") {
				p = "/" + p
			}
			req.URL.Path = p
		},
	}

	return func(c *gin.Context) {
		proxy.ServeHTTP(c.Writer, c.Request)
	}
}

func registerU2Routes(r *gin.Engine) {
	if os.Getenv("U2_DISABLE") != "" {
		return
	}
	h := u2ProxyHandler()
	r.Any("/u2", h)
	r.Any("/u2/*filepath", h)
}
