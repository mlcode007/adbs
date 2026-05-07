<template>
  <el-container>
    <el-header class="header">
      <span>Adbs</span>
      <span class="header-actions">
        <el-button type="text" @click="$router.push('/server-verify')">服务器校验</el-button>
        <el-button type="text" @click="logout">退出登录</el-button>
      </span>
    </el-header>
    <el-main>
      <el-row>
        <el-col :span="18" :offset="3">
          <DevicesList></DevicesList>
        </el-col>
      </el-row>
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
  margin-top: 10px;
}
.header-actions .el-button {
  margin-left: 4px;
}
</style>


<script>
// @ is an alias to /src
import DevicesList from '@/components/DevicesList.vue'
import devices from '@/api/devices'
import { clearToken } from '@/utils/auth'

// https://github.com/xtermjs/xterm.js/issues/573
export default {
  name: 'home',
  components: {
    DevicesList
  },
  methods: {
    getList: function() {
      devices.lists()
    },
    logout() {
      clearToken()
      this.$router.replace('/login')
    }
  }
}
</script>
