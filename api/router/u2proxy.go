package router

import (
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

// u2BackendURL 为 python_u2_bridge（uvicorn）监听地址，仅本机回环，由 Go 在 ADBS_PORT（默认 18081）上以 /u2 对外转发。
// 环境变量：
//
//	U2_BACKEND          完整 URL，如 http://127.0.0.1:18082（优先级最高）
//	U2_INTERNAL_PORT    未设置 U2_BACKEND 时使用，默认 18082
//	U2_DIAL_TIMEOUT     建连超时，秒，默认 5
//	U2_HEADER_TIMEOUT   等待上游返回 header 超时，秒，默认 60
//	U2_IDLE_TIMEOUT     连接池空闲超时，秒，默认 90
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

// envDurationSeconds 读取秒级整数环境变量，失败回退 def。
func envDurationSeconds(name string, def time.Duration) time.Duration {
	v := strings.TrimSpace(os.Getenv(name))
	if v == "" {
		return def
	}
	n, err := strconv.Atoi(v)
	if err != nil || n <= 0 {
		return def
	}
	return time.Duration(n) * time.Second
}

func u2ProxyTransport() *http.Transport {
	dialTimeout := envDurationSeconds("U2_DIAL_TIMEOUT", 5*time.Second)
	headerTimeout := envDurationSeconds("U2_HEADER_TIMEOUT", 60*time.Second)
	idleTimeout := envDurationSeconds("U2_IDLE_TIMEOUT", 90*time.Second)

	return &http.Transport{
		Proxy: http.ProxyFromEnvironment,
		DialContext: (&net.Dialer{
			Timeout:   dialTimeout,
			KeepAlive: 30 * time.Second,
		}).DialContext,
		ForceAttemptHTTP2:     false,
		MaxIdleConns:          100,
		MaxIdleConnsPerHost:   32,
		IdleConnTimeout:       idleTimeout,
		TLSHandshakeTimeout:   5 * time.Second,
		ExpectContinueTimeout: 1 * time.Second,
		ResponseHeaderTimeout: headerTimeout,
	}
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
		Transport: u2ProxyTransport(),
		// 上游不可达 / 超时 / 连接被对端关闭时，包装成结构化 JSON，避免回客户端的是空白 502。
		ErrorHandler: func(w http.ResponseWriter, r *http.Request, err error) {
			log.Printf("u2 proxy error: %s %s -> %v", r.Method, r.URL.Path, err)
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
			w.WriteHeader(http.StatusBadGateway)
			_, _ = w.Write([]byte(`{"ok":false,"error":"u2 backend unavailable","detail":` +
				strconv.Quote(err.Error()) + `}`))
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
