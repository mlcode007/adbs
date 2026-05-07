<template>
  <div class="console" id="terminal"></div>
</template>

<style scoped>
#app {
    margin-top: 0;
}
</style>


<script>
// @ is an alias to /src
import Terminal from '@/plugins/xterm.js'
import {shell} from '@/api/websocket.js'

// https://github.com/xtermjs/xterm.js/issues/573
export default {
  name: 'Console',
  data() {
    return {
      terminalSocket: null,
      term: null,
      serial: ""
    }
  },
  methods: {
    ab2str(buf) {
        return String.fromCharCode.apply(null, new Uint8Array(buf));
    }
  },
  mounted() {
    this.serial = this.$route.query.serial
    let terminalContainer = document.getElementById('terminal')
    // open websocket
    this.terminalSocket = shell(this.serial)
    this.terminalSocket.binaryType = "arraybuffer";
    this.terminalSocket.onopen = () => {
        this.term = new Terminal({
            screenKeys: true,
            useStyle: true,
            cursorBlink: true,
            rightClickSelectsWord: true,
            rows: 40,
        });
        this.term.write("\n\n\x1b[33mwelcome to " + this.serial + "!\x1b[0m\r\n\n")
        this.term.on('data', (data) => {
            this.terminalSocket.send(new TextEncoder().encode("\x00" + data));
        });
        this.term.on('resize', (evt) => {
            this.terminalSocket.send(new TextEncoder().encode("\x01" + JSON.stringify({cols: evt.cols, rows: evt.rows})))
        });
        this.term.on('title', function(title) {
            document.title = title;
        });
        this.term.open(terminalContainer);
        this.term.fit();
        this.term.toggleFullScreen();
    };
    this.terminalSocket.onmessage = (evt) =>{
        if (evt.data instanceof ArrayBuffer) {
            this.term.write(this.ab2str(evt.data));
        } else {
            alert(evt.data)
        }
    };
    this.terminalSocket.onclose = () => {
        this.term.write("Session terminated");
        this.term.destroy();
        this.$route.go(-1);
    };
    this.terminalSocket.onerror = (evt) => {
        this.term.write("WebSocket Session Error: " + evt);
    }
  },
  beforeDestroy() {
    this.terminalSocket.close()
    this.term.destroy()
  }
}
</script>
