<template>
  <div>
    <el-button type="primary" size="mini" style="float:right;" @click="connectFormVisible = true">连接设备</el-button>
    <el-table
      :data="tableData.filter(data => !search || data.no.toLowerCase().includes(search.toLowerCase()))"
      style="width: 100%">
      <el-table-column
        label="唯一标识符"
        prop="serial">
      </el-table-column>
      <el-table-column
        label="状态"
        prop="state">
      </el-table-column>
      <el-table-column
        label="型号"
        prop="model">
      </el-table-column>
      <el-table-column
        label="设备"
        prop="device">
      </el-table-column>
      <el-table-column
        label="平台"
        prop="product">
      </el-table-column>
      <el-table-column
        align="right">
        <template slot="header">
          <el-input
            v-model="search"
            size="mini"
            placeholder="输入关键字搜索"/>
        </template>
        <template slot-scope="scope">
          <el-button
            size="mini"
            @click="handleShell(scope.$index, scope.row)">Shell</el-button>
          <el-button
            size="mini" type="primary"
            @click="handleCtrl(scope.$index, scope.row)">控制</el-button>
          <el-button
            size="mini"
            type="danger"
            @click="handleDelete(scope.$index, scope.row)">断开</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog title="连接设备" :visible.sync="connectFormVisible" :before-close="connectFormCloseEvent">
      <el-form>
        <el-form-item label="设备IP">
          <el-input v-model="connectIp" autocomplete="off"></el-input>
        </el-form-item>
      </el-form>
      <div slot="footer" class="dialog-footer">
        <el-button type="primary" :loading="connectLoading" @click="connectDevice">连 接</el-button>
      </div>
    </el-dialog>
  </div>

</template>

<script>
  import { lists,connect,disConnect } from '../api/devices.js'
  
  export default {
    data() {
      return {
        connectFormVisible: false,
        connectLoading: false,
        connectIp: "",
        tableData: [],
        search: ''
      }
    },
    mounted(){
      this.loadList()
    },
    methods: {
      loadList() {
        lists().then( (res) => {
          this.tableData = res.data
        })
      },
      handleShell(index, row) {
        this.$router.push({ path: 'terminal', query: { serial: row.serial}})
      },
      handleDelete(index, row) {
        disConnect(row.serial).then(res => {
          this.$message('断开成功' + (res.data && res.data.message ? ': ' + res.data.message : ''));
          this.loadList()
        }).catch(error => {
          this.$message.error((error.response && error.response.data && error.response.data.message) || error.message || '断开失败');
        })
      },
      handleCtrl(index, row) {
        this.$router.push({ path: 'control', query: { serial: row.serial}})
      },
      connectDevice() {
        this.connectLoading = true;
        connect(this.connectIp).then((res) => {
          this.$message('连接成功' + (res.data && res.data.message ? ': ' + res.data.message : ''));
          this.loadList()
          this.connectFormVisible = false
        }).catch(error => {
          let msg = (error.response && error.response.data && error.response.data.message) || error.message || '连接错误，请重试'
          if (error.code === 'ECONNABORTED') {
            msg = '设备连接失败：等待响应超时'
          }
          this.$message.error(msg)
        }).finally(() => {
          this.connectLoading = false;
        })
      },
      connectFormCloseEvent(done) {
        this.connectLoading = false;
        done()
      }
    },
  }
</script>