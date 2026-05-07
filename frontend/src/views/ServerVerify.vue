<template>
  <el-container>
    <el-header class="header">
      <span>服务器校验</span>
      <span class="header-actions">
        <el-button size="small" type="primary" :loading="loading" @click="load">重新检测</el-button>
        <el-button size="small" @click="$router.push('/')">返回首页</el-button>
      </span>
    </el-header>
    <el-main>
      <el-alert
        v-if="error"
        :title="error"
        type="error"
        show-icon
        :closable="false"
        style="margin-bottom: 16px"
      />
      <el-descriptions v-if="data" :column="1" border size="medium">
        <el-descriptions-item label="当前时间">{{ data.server_time }}</el-descriptions-item>
        <el-descriptions-item v-if="data.hostname" label="主机名">{{ data.hostname }}</el-descriptions-item>
        <el-descriptions-item label="Go 版本">{{ data.go_version }}</el-descriptions-item>
        <el-descriptions-item label="监听端口">{{ data.listen_port }}</el-descriptions-item>
        <el-descriptions-item label="GOPROXY">{{ data.goproxy || '（未设置）' }}</el-descriptions-item>
        <el-descriptions-item label="U2 已禁用">{{ data.u2_disabled ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="ADB 服务 (5037)">
          <el-tag :type="data.adb_server && data.adb_server.ok ? 'success' : 'danger'" size="small">
            {{ data.adb_server && data.adb_server.ok ? '正常' : '异常' }}
          </el-tag>
          <span class="detail">{{ data.adb_server && data.adb_server.detail }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="adb 命令行">
          <el-tag :type="data.adb_cli && data.adb_cli.ok ? 'success' : 'danger'" size="small">
            {{ data.adb_cli && data.adb_cli.ok ? '正常' : '异常' }}
          </el-tag>
          <span class="detail">{{ data.adb_cli && data.adb_cli.detail }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="U2 后端 (本机)">
          <el-tag :type="data.u2_backend && data.u2_backend.ok ? 'success' : 'warning'" size="small">
            {{ data.u2_backend && data.u2_backend.ok ? '可达' : '异常' }}
          </el-tag>
          <span class="detail">{{ data.u2_backend && data.u2_backend.detail }}</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-main>
  </el-container>
</template>

<style scoped>
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  line-height: 60px;
  height: 60px !important;
}
.header-actions .el-button + .el-button {
  margin-left: 8px;
}
.detail {
  margin-left: 8px;
  color: #606266;
  word-break: break-all;
}
</style>

<script>
export default {
  name: 'ServerVerify',
  data() {
    return {
      loading: false,
      data: null,
      error: ''
    }
  },
  mounted() {
    this.load()
  },
  methods: {
    load() {
      this.loading = true
      this.error = ''
      this.$axios
        .get('/api/server/verify')
        .then(res => {
          this.data = res.data
        })
        .catch(err => {
          this.data = null
          this.error =
            (err.response && err.response.data && err.response.data.message) ||
            err.message ||
            '请求失败'
        })
        .finally(() => {
          this.loading = false
        })
    }
  }
}
</script>
