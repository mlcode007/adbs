package handlers

import (
	"net/http"

	"adbs/shell"

	"github.com/gin-gonic/gin"
)

// Input 向设备发送事件（多机时请传 serial，与 adb devices 中一致）
func Input(c *gin.Context) {
	serial := c.PostForm("serial")
	if serial == "" {
		serial = c.Query("serial")
	}
	command := c.PostForm("command")
	arg := c.PostForm("arg")

	_, err := shell.Input(serial, command, arg)
	if err != nil {
		c.JSON(http.StatusGatewayTimeout, gin.H{"message": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"message": "success"})
}
