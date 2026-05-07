const { defineConfig } = require('@vue/cli-service')
const path = require('path')

// 生产构建直接写入 ../static，由 Gin r.Static("/static", "static") 提供资源；无需再拷贝 dist
module.exports = defineConfig({
  transpileDependencies: true,
  publicPath: process.env.NODE_ENV === 'production' ? '/static/' : '/',
  outputDir: path.resolve(__dirname, '../static'),
  devServer: {
    port: 8090,
    proxy: {
      '/api': { target: 'http://127.0.0.1:18081', changeOrigin: true },
      '/u2': { target: 'http://127.0.0.1:18081', changeOrigin: true },
      '/static': { target: 'http://127.0.0.1:18081', changeOrigin: true }
    }
  }
})
