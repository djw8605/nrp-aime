/**
 * Portal authentication API helpers.
 */
import apiClient from './client'

/**
 * Return current auth session state.
 * @returns {Promise<Object>}
 */
export function fetchAuthSession() {
  return apiClient.get('/auth/session').then((res) => res.data)
}

/**
 * Build backend login URL for admin portal flow.
 * @param {string} nextPath
 * @returns {string}
 */
export function buildPortalLoginUrl(nextPath = '/') {
  const encoded = encodeURIComponent(nextPath || '/')
  return `/api/v1/auth/login?next=${encoded}`
}

/**
 * Clear current portal session.
 * @returns {Promise<Object>}
 */
export function logoutPortal() {
  return apiClient.post('/auth/logout').then((res) => res.data)
}
