package handlers

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os/exec"
	"strconv"
	"strings"
	"time"

	"adbs/adbkit"
	"adbs/shell"

	"github.com/gin-gonic/gin"
)

const CLENT_IP = "127.0.0.1"
const CLENT_PORT = 5037

const adbConnectTimeout = 5 * time.Second

// GetDevices 获取多个项目
func GetDevices(c *gin.Context) {
	// 设备列表
	devices, err := adbkit.New(CLENT_IP, CLENT_PORT).Lists()
	if err != nil {
		c.JSON(http.StatusOK, gin.H{
			"message": fmt.Sprintf("devices error: %s", err.Error()),
		})
	} else {
		if len(devices) == 0 {
			c.JSON(http.StatusOK, make([]string, 0))
		} else {
			c.JSON(http.StatusOK, devices)
		}
	}
}

// ConnectDevice 连接设备：与本机手动执行 `adb connect IP[:端口]` 一致（默认端口 5555），无需先在终端连过。
func ConnectDevice(c *gin.Context) {
	raw := strings.TrimSpace(c.PostForm("ip"))
	if raw == "" {
		c.JSON(http.StatusOK, gin.H{"message": "IP Empty"})
		return
	}
	addr := raw
	if !strings.Contains(addr, ":") {
		addr = addr + ":5555"
	}

	ctx, cancel := context.WithTimeout(context.Background(), adbConnectTimeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, "adb", "connect", addr)
	out, err := cmd.CombinedOutput()
	outStr := strings.TrimSpace(string(out))
	lower := strings.ToLower(outStr)
	if err != nil {
		if errors.Is(err, context.DeadlineExceeded) || errors.Is(ctx.Err(), context.DeadlineExceeded) {
			c.JSON(http.StatusRequestTimeout, gin.H{
				"message": "设备连接失败：5秒内无响应，请检查地址或设备是否在线",
			})
			return
		}
		c.JSON(http.StatusBadRequest, gin.H{
			"message": fmt.Sprintf("adb connect 失败: %v", err),
			"output":  outStr,
		})
		return
	}
	if strings.Contains(lower, "failed to connect") || strings.Contains(lower, "cannot connect") ||
		strings.Contains(lower, "unable to connect") {
		c.JSON(http.StatusBadRequest, gin.H{"message": outStr, "output": outStr})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "success", "output": outStr})
}

// DisconnectDevice 断开设备
func DisconnectDevice(c *gin.Context) {
	var message = "success"

	serial := c.PostForm("serial")
	// 检查 serial 是否合法

	bo, err := shell.Disconnect(serial)
	if err != nil || !bo {
		message = fmt.Sprintf("devices connect: %s", err.Error())
	}
	c.JSON(http.StatusOK, gin.H{
		"message": message,
	})
}

// Screencap 截屏
func Screencap(c *gin.Context) {
	serial := c.Query("serial")
	channel := c.Query("channel")

	var buffer []byte
	var err error
	if channel == "shell" {
		buffer, err = shell.Screencap(serial)
	} else {
		buffer, err = adbkit.New(CLENT_IP, CLENT_PORT).Screencap(serial)
	}

	if err == nil {
		c.Writer.Header().Set("Content-Type", "image/png")
		c.Writer.Header().Set("Content-Length", strconv.Itoa(len(buffer)))
		if _, err := c.Writer.Write(buffer); err != nil {
			log.Println("unable to write image.")
		}
	} else {
		c.String(http.StatusOK, err.Error())
	}

}

// WindowSize 获取设备屏幕大小
func WindowSize(c *gin.Context) {
	serial := c.Query("serial")
	w, h, err := adbkit.New(CLENT_IP, CLENT_PORT).ScreenSize(serial)
	if err == nil {
		c.JSON(http.StatusOK, gin.H{"width": w, "height": h})
	} else {
		c.JSON(http.StatusBadGateway, gin.H{"message": err.Error()})
	}

}
