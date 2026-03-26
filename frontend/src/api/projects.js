/**
 * Project-related API calls.
 */
import apiClient from './client'

/**
 * Fetch all projects.
 * @param {boolean} includeDebug
 * @returns {Promise<Array>}
 */
export function fetchProjects(includeDebug = false) {
  return apiClient
    .get('/projects/', { params: { include_debug: includeDebug } })
    .then((res) => res.data)
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
 * Update a project.
 * @param {string} id
 * @param {Object} payload
 * @returns {Promise<Object>}
 */
export function updateProject(id, payload) {
  return apiClient.patch(`/projects/${id}`, payload).then((res) => res.data)
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
 * Fetch packets related to a project's creation or updates.
 * @param {string} id
 * @returns {Promise<Array>}
 */
export function fetchProjectPackets(id) {
  return apiClient.get(`/projects/${id}/packets`).then((res) => res.data)
}

/**
 * Add a person to a project.
 * @param {string} id
 * @param {Object} payload
 * @returns {Promise<Object>}
 */
export function addProjectMember(id, payload) {
  return apiClient.post(`/projects/${id}/members`, payload).then((res) => res.data)
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
 * Soft-delete a project (marks it inactive, does not delete users).
 * @param {string} id
 * @returns {Promise<void>}
 */
export function deleteProject(id) {
  return apiClient.delete(`/projects/${id}`)
}

/**
 * Provision project namespace + authentik group.
 * @param {string} id
 * @returns {Promise<Object>}
 */
export function provisionProjectInfrastructure(id) {
  return apiClient
    .post(`/projects/${id}/provision-infrastructure`)
    .then((res) => res.data)
}

/**
 * Run cross-service audit checks.
 * @returns {Promise<Object>}
 */
export function runAudit() {
  return apiClient.post('/audit/run').then((res) => res.data)
}

/**
 * Compare (and optionally reconcile) portal namespace memberships vs database.
 * @param {boolean} applyChanges
 * @returns {Promise<Object>}
 */
export function syncPortalNamespaceMemberships(applyChanges = false) {
  return apiClient
    .post('/audit/portal-sync', { apply_changes: Boolean(applyChanges) })
    .then((res) => res.data)
}

/**
 * Inject demo packet(s) for interface testing.
 * @param {string} scenario
 * @returns {Promise<Object>}
 */
export function sendDemoPacket(scenario = 'project_and_account') {
  return apiClient.post('/demo/send', { scenario }).then((res) => res.data)
}

/**
 * Refresh stub accounting usage snapshots for all projects.
 * @returns {Promise<Object>}
 */
export function refreshAccountingStubs() {
  return apiClient.post('/projects/accounting/stub-sync').then((res) => res.data)
}
