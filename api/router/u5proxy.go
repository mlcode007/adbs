package router

import (
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strings"

	"github.com/gin-gonic/gin"
)

// u5BackendURL 为本机附加服务监听地址，由 Go 在 ADBS_PORT（默认 18081）上以 /u5-bridge 对外转发。
// 控制台 SPA 占用路径 /u5/* ，勿与本代理共用前缀。
// 环境变量：
//
//	U5_BACKEND     完整 URL，如 http://127.0.0.1:18085（优先级最高）
//	U5_INTERNAL_PORT  未设置 U5_BACKEND 时使用，默认 18085
func u5BackendURL() string {
	if v := os.Getenv("U5_BACKEND"); v != "" {
		return v
	}
	port := os.Getenv("U5_INTERNAL_PORT")
	if port == "" {
		port = "18085"
	}
	return "http://127.0.0.1:" + port
}

func u5ProxyHandler() gin.HandlerFunc {
	target, err := url.Parse(u5BackendURL())
	if err != nil {
		return func(c *gin.Context) {
			c.JSON(http.StatusServiceUnavailable, gin.H{"message": "invalid U5_BACKEND"})
		}
	}

	proxy := &httputil.ReverseProxy{
		Director: func(req *http.Request) {
			req.URL.Scheme = target.Scheme
			req.URL.Host = target.Host
			req.Host = target.Host

			p := strings.TrimPrefix(req.URL.Path, "/u5-bridge")
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

func registerU5BridgeRoutes(r *gin.Engine) {
	if os.Getenv("U5_DISABLE") != "" {
		return
	}
	h := u5ProxyHandler()
	r.Any("/u5-bridge", h)
	r.Any("/u5-bridge/*filepath", h)
}
