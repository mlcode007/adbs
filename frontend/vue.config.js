const { defineConfig } = require('@vue/cli-service')
const path = require('path')

// 生产构建写入 ../static；publicPath 使用相对路径 ./ ，脚本与样式会相对「当前页面 URL」加载：
// 访问 https://host/u5/ → /u5/assets/... ；访问 https://host/u2/xxx → 同源相对路径。
// 无需再配 VUE_APP_PUBLIC_PATH。本地直连 Gin 根路径 / 时配套 Gin 已挂载 /assets → static/assets。
module.exports = defineConfig({
  transpileDependencies: true,
  publicPath: process.env.NODE_ENV === 'production' ? './' : '/',
  outputDir: path.resolve(__dirname, '../static'),
  devServer: {
    port: 8090,
    proxy: {
      '/api': { target: 'http://127.0.0.1:18081', changeOrigin: true },
      '/u2': { target: 'http://127.0.0.1:18081', changeOrigin: true },
      '/u5': { target: 'http://127.0.0.1:18081', changeOrigin: true },
      '/static': { target: 'http://127.0.0.1:18081', changeOrigin: true }
    }
  }
})
