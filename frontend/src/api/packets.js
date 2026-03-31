/**
 * Packet log API calls.
 */
import apiClient from './client'

/**
 * Fetch packet logs with paging, sorting, and optional filters.
 * @param {object} params
 * @returns {Promise<{items: Array, total: number, page: number, page_size: number}>}
 */
export function fetchPacketLogs(params = {}) {
  const {
    page = 1,
    pageSize = 100,
    sortBy = 'received_at',
    sortOrder = 'desc',
    q = '',
    status = '',
    direction = '',
  } = params

  return apiClient
    .get('/packets/logs', {
      params: {
        page,
        page_size: pageSize,
        sort_by: sortBy,
        sort_order: sortOrder,
        q: q || undefined,
        status: status || undefined,
        direction: direction || undefined,
      },
    })
    .then((res) => res.data)
}

/**
 * Fetch one packet log row by ID.
 * @param {string} packetId
 * @returns {Promise<object>}
 */
export function fetchPacketLog(packetId) {
  return apiClient.get(`/packets/logs/${packetId}`).then((res) => res.data)
}

/**
 * Submit a manual packet entry for ingestion.
 * @param {object} payload
 * @returns {Promise<object>}
 */
export function submitManualPacket(payload) {
  return apiClient.post('/packets/manual', payload).then((res) => res.data)
}

/**
 * Dry-run packet validation without ingesting.
 * @param {object} rawPacket
 * @returns {Promise<object>}
 */
export function validatePacket(rawPacket) {
  return apiClient.post('/packets/validate', { raw_packet: rawPacket }).then((res) => res.data)
}

/**
 * Re-ingest one packet from packet log.
 * @param {string} packetId
 * @returns {Promise<object>}
 */
export function reingestPacket(packetId) {
  return apiClient.post(`/packets/logs/${packetId}/reingest`).then((res) => res.data)
}

/**
 * Fetch transaction-centric packet summary.
 * @param {number|string} transactionId
 * @returns {Promise<object>}
 */
export function fetchTransactionSummary(transactionId) {
  return apiClient.get(`/packets/transactions/${transactionId}`).then((res) => res.data)
}

/**
 * Replay (reprocess) all packets in a transaction.
 * @param {number|string} transactionId
 * @returns {Promise<object>}
 */
export function replayTransaction(transactionId) {
  return apiClient.post(`/packets/transactions/${transactionId}/replay`).then((res) => res.data)
}
