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
      },
    })
    .then((res) => res.data)
}
