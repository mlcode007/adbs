<template>
  <el-container>
    <el-header class="header">{{serial}}</el-header>
    <el-container>
      <el-aside width="500px">
          <Screencap :serial="serial"></Screencap>
      </el-aside>
        <el-main>
            <el-row>
                <el-col :span="20" >
                    
                </el-col>
            </el-row>
        </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.header {
    margin-top: 10px;
    height: 50px;
}
</style>


<script>
// @ is an alias to /src
import Screencap from '@/components/Screencap.vue'

// https://github.com/xtermjs/xterm.js/issues/573
export default {
  name: 'control',
  data() {
    return {
      serial: ''
    }
  },
  components: {
    Screencap
  },
  methods: {

  },
  created() {
    this.serial = this.$route.query.serial
  }
}
</script>
