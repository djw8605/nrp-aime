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
 * Create a new user.
 * @param {{ email: string, name: string }} payload
 * @returns {Promise<Object>}
 */
export function createUser(payload) {
  return apiClient.post('/users/', payload).then((res) => res.data)
}
