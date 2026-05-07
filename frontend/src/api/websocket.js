import { getToken } from '@/utils/auth'

export const shell = serial => {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  const token = getToken()
  const q = 'serial=' + encodeURIComponent(serial || '') + (token ? '&token=' + encodeURIComponent(token) : '')
  return new WebSocket(proto + '//' + host + '/api/device/shell/ws?' + q)
}

export default {
    shell
}