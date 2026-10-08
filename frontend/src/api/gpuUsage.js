/**
 * GPU usage ledger API calls (daily GPU usage reported to ACCESS).
 */
import apiClient from './client'

/**
 * Fetch GPU usage records, e.g. to review ACCESS reporting failures.
 * @param {Object} options
 * @param {string[]} [options.statuses] - any of failed, pending, submitted, loaded
 * @param {string|null} [options.projectId] - restrict to one project
 * @param {number} [options.limit]
 * @returns {Promise<Array>}
 */
export function fetchGpuUsageRecords({ statuses = ['failed'], projectId = null, limit = 200 } = {}) {
  return apiClient
    .get('/gpu-usage/', {
      params: { status: statuses, project_id: projectId, limit },
      // Repeat the key (status=failed&status=pending) instead of status[]=...
      paramsSerializer: { indexes: null },
    })
    .then((res) => res.data)
}
