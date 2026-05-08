package router

import (
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
)

// u3BackendURL 为本机后端监听地址，由 Go 在 ADBS_PORT（默认 18081）上以 /u3 对外转发。
// 环境变量：
//   U3_BACKEND     完整 URL，如 http://127.0.0.1:18083（优先级最高）
//   U3_INTERNAL_PORT  未设置 U3_BACKEND 时使用，默认 18083
func u3BackendURL() string {
	if v := os.Getenv("U3_BACKEND"); v != "" {
		return v
	}
	port := os.Getenv("U3_INTERNAL_PORT")
	if port == "" {
		port = "18083"
	}
	return "http://127.0.0.1:" + port
}

func u3ProxyHandler() gin.HandlerFunc {
	target, err := url.Parse(u3BackendURL())
	if err != nil {
		return func(c *gin.Context) {
			c.JSON(http.StatusServiceUnavailable, gin.H{"message": "invalid U3_BACKEND"})
		}
	}

	proxy := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL.Scheme = target.Scheme
			req.URL.Host = target.Host
			req.Host = target.Host

			p := strings.TrimPrefix(req.URL.Path, "/u3")
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

func registerU3Routes(r *gin.Engine) {
	if os.Getenv("U3_DISABLE") != "" {
		return
	}
	h := u3ProxyHandler()
	r.Any("/u3", h)
	r.Any("/u3/*filepath", h)
}
