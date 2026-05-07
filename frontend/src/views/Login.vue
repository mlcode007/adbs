<template>
  <div class="login-wrap">
    <el-card class="login-card" shadow="hover">
      <div slot="header">Adbs 控制台登录</div>
      <el-form :model="form" :rules="rules" ref="formRef" label-width="80px" @submit.native.prevent="submit">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" autocomplete="username" clearable />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" autocomplete="current-password" show-password clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" native-type="submit" style="width:100%">登录</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(160deg, #f0f4f8 0%, #e2e8f0 100%);
}
.login-card {
  width: 400px;
  max-width: 92vw;
}
</style>

<script>
import { setToken } from '@/utils/auth'

export default {
  name: 'Login',
  data() {
    return {
      loading: false,
      form: {
        username: '',
        password: ''
      },
      rules: {
        username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
        password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
      }
    }
  },
  methods: {
    submit() {
      this.$refs.formRef.validate(valid => {
        if (!valid) return
        this.loading = true
        this.$axios
          .post('/api/auth/login', {
            username: this.form.username,
            password: this.form.password
          })
          .then(res => {
            if (res.data && res.data.token) {
              setToken(res.data.token)
              const redirect = this.$route.query.redirect
              this.$router.replace(redirect && typeof redirect === 'string' ? redirect : '/')
            } else {
              this.$message.error('登录响应异常')
            }
          })
          .catch(err => {
            const msg =
              (err.response && err.response.data && err.response.data.message) ||
              err.message ||
              '登录失败'
            this.$message.error(msg)
          })
          .finally(() => {
            this.loading = false
          })
      })
    }
  }
}
</script>
