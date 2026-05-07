import { config } from '../plugins/axios.js'

export const shell = serial => {
    return new WebSocket(  window.location.protocol === "https:" ? "wss://" : "ws://" + window.location.hostname + ":" + window.location.port +  '/api/device/shell/ws?serial=' + serial)
}

export default {
    shell
}