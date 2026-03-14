/**
 * Project-related API calls.
 */
import apiClient from './client'

/**
 * Fetch all projects.
 * @returns {Promise<Array>}
 */
export function fetchProjects() {
  return apiClient.get('/projects/').then((res) => res.data)
}

/**
 * Fetch aggregate project KPIs.
 * @returns {Promise<Object>}
 */
export function fetchProjectsSummary() {
  return apiClient.get('/projects/summary').then((res) => res.data)
}

/**
 * Fetch a single project by ID.
 * @param {string} id
 * @returns {Promise<Object>}
 */
export function fetchProject(id) {
  return apiClient.get(`/projects/${id}`).then((res) => res.data)
}

/**
 * Fetch users assigned to a project.
 * @param {string} id
 * @returns {Promise<Array>}
 */
export function fetchProjectUsers(id) {
  return apiClient.get(`/projects/${id}/users`).then((res) => res.data)
}

/**
 * Fetch resource usage for a project.
 * @param {string} id
 * @returns {Promise<Object>}
 */
export function fetchProjectUsage(id) {
  return apiClient.get(`/projects/${id}/usage`).then((res) => res.data)
}

/**
 * Trigger account creation emails for all project users.
 * @param {string} id
 * @returns {Promise<Object>}
 */
export function sendAccountEmail(id) {
  return apiClient.post(`/projects/${id}/send-account-email`).then((res) => res.data)
}

/**
 * Run cross-service audit checks.
 * @returns {Promise<Object>}
 */
export function runAudit() {
  return apiClient.post('/audit/run').then((res) => res.data)
}

/**
 * Inject demo packet(s) for interface testing.
 * @param {string} scenario
 * @returns {Promise<Object>}
 */
export function sendDemoPacket(scenario = 'project_and_account') {
  return apiClient.post('/demo/send', { scenario }).then((res) => res.data)
}
