import Vue from 'vue';

export const lists = params => {
    return Vue.axios.get("/api/devices", { params: params })
}

export const windowSize = (params) => {
    return Vue.axios.get("/api/device/window/size", { params: params })
}

export const disConnect = (serial) => {
    return Vue.axios.post("/api/devices/disconnect", "serial="+encodeURIComponent(serial), {
        headers: {
              'Content-Type': 'application/x-www-form-urlencoded'
        }
    })
}

export const connect = (ip) => {
    return Vue.axios.post("/api/devices/connect", "ip="+encodeURIComponent(ip), {
        headers: {
              'Content-Type': 'application/x-www-form-urlencoded'
        },
        timeout: 8000
    })
}

export default {
    lists,
    windowSize,
    connect,
    disConnect
}