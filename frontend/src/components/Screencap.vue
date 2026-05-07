<template>
  <img v-bind:src="imageSrc" :style="'width: '+ width +';height: ' + height + ';' "/>
</template>

<script>
import { windowSize } from '../api/devices.js'
import { config } from '../plugins/axios.js'
import { getToken } from '@/utils/auth'

function screencapURL(serial, bust) {
  const base = (config.baseURL || '') + '/api/device/screencap?channel=shell&serial=' + encodeURIComponent(serial || '')
  const t = getToken()
  const auth = t ? '&token=' + encodeURIComponent(t) : ''
  const cache = bust ? '&time=' + new Date().getTime() : ''
  return base + auth + cache
}

export default {
    name: 'Screencap',
    data() {
    return {
      imageSrc: '',
      width: "200px",
      height: "400px"
    }
  },
  created: function () {
    setInterval(this.timer, 10000);
  },
  methods: {
    timer: function () {
        this.imageSrc = screencapURL(this.serial, true)
    }
  },
  props: {
    serial: String
  },
  mounted() {
    windowSize({serial: this.serial}).then((res) => {
      if(res.data.height > res.data.width)  {
        var x = res.data.height  * 200;
        var h = x / res.data.width ;
        this.width = "200px"
        this.height = h + "px"
      } else {
        var x =res.data.width  * 200;
        var w = x /  res.data.height ;
        this.height = "200px"
        this.width = w + "px"
      }

    });
    this.imageSrc = screencapURL(this.serial, false)
  }
}
</script>