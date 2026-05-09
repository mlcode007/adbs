package router

import (
	"fmt"
	"net/http"
	"os"
	"strings"

	"adbs/api/handlers"
	"adbs/api/middleware"

	"github.com/gin-gonic/gin"
)

func Init() *gin.Engine {
	r := gin.New()

	r.Use(gin.Logger())
	r.Use(gin.Recovery())

	// 开启跨域
	r.Use(Cors())

	// 开启压缩
	//r.Use(gzip.Gzip(gzip.DefaultCompression))
	gin.SetMode("debug")

	// uiautomator2 HTTP 桥：统一走 Go 监听端口（默认 :18081）/u2 → 本机 uvicorn（默认 127.0.0.1:18082）
	registerU2Routes(r)
	// 控制台 SPA：/u5/* 映射整个 static（含 js/css/assets，勿与 /u5-bridge 混用）
	registerU5SPARoutes(r)
	// 附加后端：/u5-bridge → 本机默认 127.0.0.1:18085（可用 U5_BACKEND / U5_INTERNAL_PORT 覆盖）
	registerU5BridgeRoutes(r)

	api := r.Group("/api")
	api.POST("/auth/login", handlers.Login)

	protected := api.Group("")
	protected.Use(middleware.AuthRequired())
	{
		protected.GET("/server/verify", handlers.GetServerVerify)

		// 设备列表管理
		devices := protected.Group("/devices")
		{
			devices.GET("", handlers.GetDevices)
			devices.POST("/connect", handlers.ConnectDevice)
			devices.POST("/disconnect", handlers.DisconnectDevice)
		}

		device := protected.Group("/device")
		{
			device.GET("/package/clear", handlers.ClearPackage)
			device.GET("/packages", handlers.GetPackages)
			device.GET("/screencap", handlers.Screencap)
			device.POST("/push", handlers.Push)
			device.GET("/pull", handlers.Pull)
			device.GET("/dir", handlers.Dir)
			device.GET("/stat", handlers.Stat)
			device.POST("/input", handlers.Input)
			device.GET("/window/size", handlers.WindowSize)
			device.POST("/install", handlers.Install)

			device.GET("/shell/ws", func(c *gin.Context) {
				handlers.WsHandler(c.Writer, c.Request)
			})
		}
	}

	// 首页优先使用 frontend 构建产物 static/index.html；未构建时回退 templates/index.html
	r.GET("/", func(c *gin.Context) {
		if _, err := os.Stat("static/index.html"); err == nil {
			c.File("static/index.html")
			return
		}
		c.File("templates/index.html")
	})

	r.Static("/static", "static")
	// 与 Vue 生产包 publicPath「./」生成的资源路径 /assets/* 对齐（首页在 / 打开时）
	r.Static("/assets", "static/assets")

	return r
}

// registerU5SPARoutes 部署在子路径 /u5 时的控制台入口（与 registerU5BridgeRoutes 分离）
func registerU5SPARoutes(r *gin.Engine) {
	r.GET("/u5", func(c *gin.Context) {
		c.Redirect(http.StatusMovedPermanently, "/u5/")
	})
	r.GET("/u5/", func(c *gin.Context) {
		if _, err := os.Stat("static/index.html"); err == nil {
			c.File("static/index.html")
			return
		}
		c.Status(http.StatusNotFound)
	})
	// Vue 构建除 assets 外还有 js/、css/ 等目录，仅挂 /u5/assets 会导致 chunk 404
	r.Static("/u5", "static")
}

func Cors() gin.HandlerFunc {
	return func(c *gin.Context) {
		method := c.Request.Method               //请求方法
		origin := c.Request.Header.Get("Origin") //请求头部
		var headerKeys []string                  // 声明请求头keys
		for k, _ := range c.Request.Header {
			headerKeys = append(headerKeys, k)
		}
		headerStr := strings.Join(headerKeys, ", ")
		if headerStr != "" {
			headerStr = fmt.Sprintf("access-control-allow-origin, access-control-allow-headers, %s", headerStr)
		} else {
			headerStr = "access-control-allow-origin, access-control-allow-headers"
		}
		if origin != "" {
			c.Writer.Header().Set("Access-Control-Allow-Origin", "*")
			c.Header("Access-Control-Allow-Origin", "*")                                       // 这是允许访问所有域
			c.Header("Access-Control-Allow-Methods", "POST, GET, OPTIONS, PUT, DELETE,UPDATE") //服务器支持的所有跨域请求的方法,为了避免浏览次请求的多次'预检'请求
			//  header的类型
			c.Header("Access-Control-Allow-Headers", "Authorization, Content-Length, X-CSRF-Token, Token,session,X_Requested_With,Accept, Origin, Host, Connection, Accept-Encoding, Accept-Language,DNT, X-CustomHeader, Keep-Alive, User-Agent, X-Requested-With, If-Modified-Since, Cache-Control, Content-Type, Pragma")
			//				允许跨域设置																										可以返回其他子段
			c.Header("Access-Control-Expose-Headers", "Content-Length, Access-Control-Allow-Origin, Access-Control-Allow-Headers,Cache-Control,Content-Language,Content-Type,Expires,Last-Modified,Pragma,FooBar") // 跨域关键设置 让浏览器可以解析
			c.Header("Access-Control-Max-Age", "172800")                                                                                                                                                           // 缓存请求信息 单位为秒
			c.Header("Access-Control-Allow-Credentials", "false")                                                                                                                                                  //	跨域请求是否需要带cookie信息 默认设置为true
			c.Set("content-type", "application/json")                                                                                                                                                              // 设置返回格式是json
		}

		//放行所有OPTIONS方法
		if method == "OPTIONS" {
			c.JSON(http.StatusOK, "Options Request!")
		}
		// 处理请求
		c.Next() //	处理请求
	}
}
