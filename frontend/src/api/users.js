/**
 * User-related API calls.
 */
import apiClient from './client'

/**
 * Fetch a user by ID.
 * @param {string} id
 * @returns {Promise<Object>}
 */
export function fetchUser(id) {
  return apiClient.get(`/users/${id}`).then((res) => res.data)
}

/**
 * Fetch all users.
 * @returns {Promise<Array>}
 */
export function fetchUsers() {
  return apiClient.get('/users/').then((res) => res.data)
}

/**
 * Fetch a user's project memberships.
 * @param {string} id
 * @returns {Promise<Array>}
 */
export function fetchUserMemberships(id) {
  return apiClient.get(`/users/${id}/memberships`).then((res) => res.data)
}

/**
 * Fetch packet-derived details for a user.
 * @param {string} id
 * @returns {Promise<Array>}
 */
export function fetchUserPacketDetails(id) {
  return apiClient.get(`/users/${id}/packet-details`).then((res) => res.data)
}

/**
 * Send a person-centric invite for a user.
 * @param {string} id
 * @param {Object} payload
 * @returns {Promise<Object>}
 */
export function sendUserInvite(id, payload) {
  return apiClient.post(`/users/${id}/invites`, payload).then((res) => res.data)
}

/**
 * Create a new user.
 * @param {{ email: string, name: string }} payload
 * @returns {Promise<Object>}
 */
export function createUser(payload) {
  return apiClient.post('/users/', payload).then((res) => res.data)
}
