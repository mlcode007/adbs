<template>
  <el-container>
    <el-header class="header">Adbs</el-header>
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
header {
  size: 20px;
  margin-top: 20px;
}
</style>


<script>
// @ is an alias to /src
import DevicesList from '@/components/DevicesList.vue'
import devices from '@/api/devices'

// https://github.com/xtermjs/xterm.js/issues/573
export default {
  name: 'home',
  components: {
    DevicesList
  },
  methods: {
    getList: function() {
      devices.lists()
    }
  }
}
</script>
