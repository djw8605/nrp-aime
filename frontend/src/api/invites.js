/**
 * Invite onboarding API calls.
 */
import apiClient from './client'

/**
 * Create invite for a project.
 * @param {string} projectId
 * @param {Object} payload
 * @returns {Promise<Object>}
 */
export function createProjectInvite(projectId, payload) {
  return apiClient.post(`/projects/${projectId}/invites`, payload).then((res) => res.data)
}

/**
 * Fetch safe invite preview information.
 * @param {string} token
 * @returns {Promise<Object>}
 */
export function previewInvite(token) {
  return apiClient
    .get('/invites/preview', {
      params: { token },
    })
    .then((res) => res.data)
}

/**
 * Build backend URL that starts invite accept + Authentik login redirect.
 * @param {string} token
 * @returns {string}
 */
export function buildInviteAcceptStartUrl(token) {
  const encoded = encodeURIComponent(token)
  return `/api/v1/invites/accept?token=${encoded}`
}
