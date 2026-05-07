package handlers

import (
	"net/http"

	"adbs/api/middleware"

	"github.com/gin-gonic/gin"
)

type loginBody struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

// Login POST /api/auth/login
func Login(c *gin.Context) {
	var body loginBody
	if err := c.ShouldBindJSON(&body); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"message": "参数错误"})
		return
	}
	if !middleware.CheckAdminCredentials(body.Username, body.Password) {
		c.JSON(http.StatusUnauthorized, gin.H{"message": "用户名或密码错误"})
		return
	}
	token := middleware.SignToken(body.Username)
	c.JSON(http.StatusOK, gin.H{"token": token})
}
