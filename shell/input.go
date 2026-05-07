package shell

import (
	"bytes"
	"os/exec"
)

// Input 用于模拟输入
// serial 为空时使用 adb 默认设备；非空则执行 adb -s <serial> shell input …
// 具体参数，参见：http://blog.bihe0832.com/adb-shell-input.html
func Input(serial, command, arg string) (bool, error) {
	var cmd *exec.Cmd
	if serial != "" {
		cmd = exec.Command("adb", "-s", serial, "shell", "input", command, arg)
	} else {
		cmd = exec.Command("adb", "shell", "input", command, arg)
	}

	//读取io.Writer类型的cmd.Stdout，再通过bytes.Buffer(缓冲byte类型的缓冲器)将byte类型转化为string类型(out.String():这是bytes类型提供的接口)
	var out bytes.Buffer
	cmd.Stdout = &out

	//Run执行c包含的命令，并阻塞直到完成。  这里stdout被取出，cmd.Wait()无法正确获取stdin,stdout,stderr，则阻塞在那了
	if err := cmd.Run(); err != nil {
		return false, err
	}
	return true, nil
}
