<template>
  <img v-bind:src="imageSrc" :style="'width: '+ width +';height: ' + height + ';' "/>
</template>

<script>
import { windowSize } from '../api/devices.js'
import { config } from '../plugins/axios.js'

export default {
  name: 'Screencap',
  data() {
    return {
      imageSrc: config.baseURL + '/api/device/screencap',
      width: "200px",
      height: "400px"
    }
  },
  created: function () {
    setInterval(this.timer, 10000);
  },
  methods: {
    timer: function () {
        this.imageSrc =  config.baseURL + "/api/device/screencap?channel=shell&serial=" + this.serial + "&time=" + new Date().getTime();
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
    this.imageSrc = config.baseURL + "/api/device/screencap?channel=shell&serial=" + this.serial;
  }
}
</script>