import Vue from 'vue'
import Router from 'vue-router'
import Home from './views/Home.vue'
import Terminal from './views/Terminal.vue'
import Control from './views/Control.vue'
import Login from './views/Login.vue'
import ServerVerify from './views/ServerVerify.vue'
import { getToken } from './utils/auth'

Vue.use(Router)

const router = new Router({
  routes: [
    {
      path: '/login',
      name: 'login',
      component: Login,
      meta: { public: true }
    },
    {
      path: '/',
      name: 'home',
      component: Home
    },
    {
      path: '/about',
      name: 'about',
      // route level code-splitting
      // this generates a separate chunk (about.[hash].js) for this route
      // which is lazy-loaded when the route is visited.
      component: () => import(/* webpackChunkName: "about" */ './views/About.vue')
    },
    {
      path: '/terminal',
      name: 'terminal',
      // route level code-splitting
      // this generates a separate chunk (about.[hash].js) for this route
      // which is lazy-loaded when the route is visited.
      component: Terminal
    },
    {
      path: '/control',
      name: 'control',
      component: Control
    },
    {
      path: '/server-verify',
      name: 'server-verify',
      component: ServerVerify
    }
  ]
})

router.beforeEach((to, from, next) => {
  if (to.meta && to.meta.public) {
    if (getToken() && to.path === '/login') {
      next({ path: '/' })
      return
    }
    next()
    return
  }
  if (!getToken()) {
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }
  next()
})

export default router
