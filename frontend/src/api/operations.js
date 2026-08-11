import request from './request'

export function getOperationLogs(params) {
  return request.get('/api/operation-logs', { params })
}
