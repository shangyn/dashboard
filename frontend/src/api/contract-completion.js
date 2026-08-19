import request from './request'

export function getRegionSummary(year, region) {
  return request.get('/api/contract-completion/region-summary', { params: { year, region } })
}

export function getModuleDetail(year, region) {
  return request.get('/api/contract-completion/module-detail', { params: { year, region } })
}

export function getSalespersonComparison(year, region) {
  return request.get('/api/contract-completion/salesperson', { params: { year, region } })
}

export function getDataStatus() {
  return request.get('/api/contract-completion/data-status')
}

export function getUnmatchedContracts() {
  return request.get('/api/contract-completion/unmatched-contracts')
}

export function getRegions() {
  return request.get('/api/contract-completion/regions')
}

export function getTwoYearComparison(includePersonal = false) {
  return request.get('/api/contract-completion/two-year-comparison', {
    params: includePersonal ? { include_personal: 1 } : {}
  })
}

export function getAnnualCompletion(includePersonal = false) {
  return request.get('/api/contract-completion/annual-completion', {
    params: includePersonal ? { include_personal: 1 } : {}
  })
}
