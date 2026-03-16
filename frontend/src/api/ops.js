/**
 * Operations/observability API calls.
 */
import apiClient from './client'

export function fetchWorkerStatuses() {
  return apiClient.get('/ops/workers/status').then((res) => res.data)
}

export function fetchFreshness() {
  return apiClient.get('/ops/freshness').then((res) => res.data)
}

export function fetchErrorBudgetMetrics() {
  return apiClient.get('/ops/metrics/error-budget').then((res) => res.data)
}

export function fetchLifecycleFunnelMetrics() {
  return apiClient.get('/ops/metrics/lifecycle-funnel').then((res) => res.data)
}

export function fetchQueueLatencyMetrics() {
  return apiClient.get('/ops/metrics/queue-latency').then((res) => res.data)
}

export function evaluateAlerts() {
  return apiClient.post('/ops/alerts/evaluate').then((res) => res.data)
}

export function fetchOutboundPacketLogs(limit = 200) {
  return apiClient
    .get('/ops/outbound-packets', { params: { limit } })
    .then((res) => res.data)
}
