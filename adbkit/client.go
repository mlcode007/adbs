package adbkit

import (
	"errors"
	"fmt"
	"io"
	"net"
	"strconv"
)

type Client struct {
	Host string
	Port int
}

// New Client 新建一个节点
func New(host string, port int) Client {
	if !CheckTcp(host, port) {
		panic(errors.New("network fail"))
	}
	return Client{Host: host, Port: port}
}

// Command 调用一个 adb host 服务命令并读取一条完整应答。
// adb 在应答后通常不关闭 TCP，若使用 ReadAll 会一直阻塞，导致 HTTP 超时；前端误报「连接失败」而设备已连上。
func (c Client) Command(command string) ([]byte, error) {
	conn, err := net.Dial("tcp", fmt.Sprintf("%s:%d", c.Host, c.Port))
	if err != nil {
		return nil, err
	}
	defer conn.Close()

	if _, err := conn.Write(EncodeCommend(command)); err != nil {
		return nil, err
	}

	header := make([]byte, 8)
	if _, err := io.ReadFull(conn, header); err != nil {
		return nil, err
	}
	status := string(header[0:4])
	if status != OKAY && status != FAIL {
		return nil, fmt.Errorf("unexpected adb status %q", status)
	}
	length, err := strconv.ParseUint(string(header[4:8]), 16, 32)
	if err != nil {
		return nil, err
	}
	const maxPayload = 64 << 20 // 64MiB
	if length > maxPayload {
		return nil, fmt.Errorf("adb payload too large: %d", length)
	}
	body := make([]byte, length)
	if length > 0 {
		if _, err := io.ReadFull(conn, body); err != nil {
			return nil, err
		}
	}
	return append(header, body...), nil
}

// CheckTcp 检查一个端口是否可以连接
func CheckTcp(host string, port int) bool {
	if _, err := net.Dial("tcp", fmt.Sprintf("%s:%d", host, port)); err != nil {
		return false
	}
	return true
}
