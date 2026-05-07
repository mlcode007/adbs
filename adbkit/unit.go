package adbkit

import (
	"fmt"
	"strconv"
	"strings"
)

// adb 同步应答中第 5～8 字节为 4 位十六进制 ASCII 长度（旧代码误用十进制 Atoi 会导致解析错误）。
func adbHexPayloadLen(resp []byte) (int, error) {
	if len(resp) < 8 {
		return 0, fmt.Errorf("adb response too short")
	}
	n, err := strconv.ParseUint(string(resp[4:8]), 16, 32)
	if err != nil {
		return 0, err
	}
	return int(n), nil
}

// EncodeCommend 对命令进行编码
func EncodeCommend(command string) []byte {
	prefix := strings.ToUpper("0000" + fmt.Sprintf("%X", len(command)))
	length := len(prefix)
	prefix = prefix[length-4 : length]
	return []byte(prefix + command)
}

// Uint32ToBytes 32位整形 转 []byte
func Uint32ToBytes(n uint32) []byte {
	return []byte{
		byte(n),
		byte(n >> 8),
		byte(n >> 16),
		byte(n >> 24),
	}
}

// IsBelong 检查IP是否属于IP段内
// fmt.Println(isBelong(`10.187.102.8`, `10.187.102.0/24`))
func IsBelong(ip, cidr string) bool {
	ipAddr := strings.Split(ip, `.`)
	if len(ipAddr) < 4 {
		return false
	}
	cidrArr := strings.Split(cidr, `/`)
	if len(cidrArr) < 2 {
		return false
	}
	var tmp = make([]string, 0)
	for key, value := range strings.Split(`255.255.255.0`, `.`) {
		iint, _ := strconv.Atoi(value)

		iint2, _ := strconv.Atoi(ipAddr[key])

		tmp = append(tmp, strconv.Itoa(iint&iint2))
	}
	return strings.Join(tmp, `.`) == cidrArr[0]
}

// Atoi 用于内部 字符串转整形
func Atoi(s string) int {
	n, _ := strconv.Atoi(s)
	return n
}
