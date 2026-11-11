import request from './request'

export function getShipTrackingContext() {
  return request.get('/api/ship-tracking/context')
}

export function getWeeklyPlan(params) {
  return request.get('/api/ship-tracking/weekly', { params })
}

export function saveWeeklyDraft(payload) {
  return request.post('/api/ship-tracking/weekly/draft', payload)
}

export function submitWeeklyPlan(payload) {
  return request.post('/api/ship-tracking/weekly/submit', payload)
}

export function withdrawWeeklyPlan(payload) {
  return request.post('/api/ship-tracking/weekly/withdraw', payload)
}

export function adjustWeeklyPlan(payload) {
  return request.post('/api/ship-tracking/weekly/adjust', payload)
}

export function addWeeklyLadder(payload) {
  return request.post('/api/ship-tracking/weekly/manual', payload)
}

export function saveWeeklyRemark(payload) {
  return request.post('/api/ship-tracking/weekly/remark', payload)
}

export function getTrackingItems(params) {
  return request.get('/api/ship-tracking/items', { params })
}

export function getTrackingHistory(ladderKey) {
  return request.get('/api/ship-tracking/history', { params: { ladder_key: ladderKey } })
}

export function recordDailyShipments(payload) {
  return request.post('/api/ship-tracking/daily', payload)
}

export function previewExternalLadders(payload) {
  return request.post('/api/ship-tracking/daily/external/preview', payload)
}

export function deleteDailyShipments(payload) {
  return request.post('/api/ship-tracking/daily/delete', payload)
}

export function unlockShipTracking(payload) {
  return request.post('/api/ship-tracking/unlock', payload)
}

export function previewPlanImport(file, planMonth) {
  const data = new FormData()
  data.append('file', file)
  if (planMonth) data.append('plan_month', planMonth)
  return request.post('/api/ship-tracking/import/plan/preview', data)
}

export function commitPlanImport(batchId, force = false, overwriteExpected = false) {
  return request.post('/api/ship-tracking/import/plan/commit', {
    batch_id: batchId,
    force,
    overwrite_expected: overwriteExpected,
  })
}

export function previewPlanFromForecast(month) {
  return request.post('/api/ship-tracking/import/plan/from-forecast/preview', { month })
}

export function commitForecastImport(batchId) {
  return request.post('/api/ship-tracking/import/plan/from-forecast/commit', { batch_id: batchId })
}

export function previewBookingImport(file) {
  const data = new FormData()
  data.append('file', file)
  return request.post('/api/ship-tracking/import/booking/preview', data)
}

export function commitBookingImport(batchId, force = false) {
  return request.post('/api/ship-tracking/import/booking/commit', { batch_id: batchId, force })
}

export function getImportBatches(dataType = '', includePreview = false) {
  return request.get('/api/ship-tracking/imports', {
    params: { data_type: dataType, include_preview: includePreview ? 1 : 0 },
  })
}

export function deleteImportBatch(batchId) {
  return request.delete(`/api/ship-tracking/imports/${batchId}`)
}

export function cleanupPreviewBatches(dataType = '') {
  return request.delete('/api/ship-tracking/imports/preview', { params: { data_type: dataType } })
}

export function getImportIssues(batchId) {
  return request.get(`/api/ship-tracking/imports/${batchId}/issues`)
}

export function downloadTrackingExport(params) {
  return request.get('/api/ship-tracking/export', { params, responseType: 'blob' })
}

export function downloadImportTemplate(type) {
  return request.get('/api/ship-tracking/import/template', {
    params: { type },
    responseType: 'blob',
  })
}

export function syncTrackingDates() {
  return request.post('/api/ship-tracking/sync')
}

export function getSyncStatus() {
  return request.get('/api/ship-tracking/sync/status')
}

export function getPaymentStatus() {
  return request.get('/api/ship-tracking/payment/status')
}

export function uploadPaymentFile(fileType, file) {
  const data = new FormData()
  data.append('file', file)
  return request.post(`/api/ship-tracking/payment/files/${fileType}`, data)
}

export function calculatePayment(background = true) {
  return request.post('/api/ship-tracking/payment/calculate', { background })
}

export function downloadPaymentReport(runId) {
  return request.get('/api/ship-tracking/payment/report', {
    params: runId ? { run_id: runId } : {},
    responseType: 'blob',
  })
}
