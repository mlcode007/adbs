const { defineConfig } = require('@vue/cli-service')
const path = require('path')

// 生产 publicPath 为 ./ ；若仅访问 /u5（无末尾 /），浏览器会把 ./assets 错解成 /assets。
// public/index.html 内联脚本按路径注入 <base href="/u5/"> 等，再加载打包资源。
// 本地根路径 / 仍走 Gin 的 /assets 挂载。
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
