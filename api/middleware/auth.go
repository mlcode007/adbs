package middleware

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

const (
	defaultAdminUser   = "admin"
	defaultAdminPass   = "1qaz2wsx"
	defaultTokenSecret = "adbs-default-change-ADBS_TOKEN_SECRET-in-production"
	tokenTTL           = 7 * 24 * time.Hour
)

func adminUser() string {
	if v := strings.TrimSpace(os.Getenv("ADBS_ADMIN_USER")); v != "" {
		return v
	}
	return defaultAdminUser
}

func adminPass() string {
	if v := os.Getenv("ADBS_ADMIN_PASS"); v != "" {
		return v
	}
	return defaultAdminPass
}

func tokenSecret() []byte {
	if v := strings.TrimSpace(os.Getenv("ADBS_TOKEN_SECRET")); v != "" {
		return []byte(v)
	}
	return []byte(defaultTokenSecret)
}

// CheckAdminCredentials 校验控制台登录账号（可用环境变量覆盖默认）。
func CheckAdminCredentials(username, password string) bool {
	return username == adminUser() && password == adminPass()
}

// SignToken 签发 HMAC 令牌。
func SignToken(username string) string {
	exp := time.Now().Add(tokenTTL).Unix()
	payload := strconv.FormatInt(exp, 10) + ":" + username
	mac := hmac.New(sha256.New, tokenSecret())
	_, _ = mac.Write([]byte(payload))
	sig := hex.EncodeToString(mac.Sum(nil))
	raw := payload + ":" + sig
	return base64.StdEncoding.EncodeToString([]byte(raw))
}

// ParseToken 解析并校验令牌，返回用户名。
func ParseToken(token string) (string, bool) {
	b, err := base64.StdEncoding.DecodeString(strings.TrimSpace(token))
	if err != nil {
		return "", false
	}
	parts := strings.Split(string(b), ":")
	if len(parts) != 3 {
		return "", false
	}
	expStr, user, sigHex := parts[0], parts[1], parts[2]
	payload := expStr + ":" + user
	mac := hmac.New(sha256.New, tokenSecret())
	_, _ = mac.Write([]byte(payload))
	wantSig, err := hex.DecodeString(sigHex)
	if err != nil || !hmac.Equal(mac.Sum(nil), wantSig) {
		return "", false
	}
	exp, err := strconv.ParseInt(expStr, 10, 64)
	if err != nil || time.Now().Unix() > exp {
		return "", false
	}
	return user, true
}

// BearerToken 从 Authorization: Bearer 或 query token 读取凭证。
func BearerToken(c *gin.Context) string {
	h := c.GetHeader("Authorization")
	if len(h) > 7 && strings.EqualFold(h[0:7], "bearer ") {
		return strings.TrimSpace(h[7:])
	}
	return strings.TrimSpace(c.Query("token"))
}

// AuthRequired 保护 /api 下需登录的接口。
func AuthRequired() gin.HandlerFunc {
	return func(c *gin.Context) {
		tok := BearerToken(c)
		if tok == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"message": "未登录或凭证已过期"})
			return
		}
		if _, ok := ParseToken(tok); !ok {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"message": "未登录或凭证已过期"})
			return
		}
		c.Next()
	}
}
