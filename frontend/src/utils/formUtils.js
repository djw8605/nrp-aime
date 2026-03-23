/**
 * Shared form helper utilities used across detail views (ProjectDetailView, PersonDetailView, etc.).
 */

export function normalizeTextValue(value) {
  const cleaned = String(value ?? '').trim()
  return cleaned || null
}

export function toNullableNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const numeric = Number(value)
  return Number.isFinite(numeric) ? numeric : null
}

export function toDateTimeLocalInput(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const offset = date.getTimezoneOffset()
  const localDate = new Date(date.getTime() - offset * 60 * 1000)
  return localDate.toISOString().slice(0, 16)
}

export function fromDateTimeLocalInput(value) {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toISOString()
}

export function parseDnList(text) {
  return String(text || '')
    .split(/\r?\n|,/)
    .map((entry) => entry.trim())
    .filter(Boolean)
}

export function parseTagList(text) {
  return String(text || '')
    .split(/\r?\n|,/)
    .map((entry) => entry.trim())
    .filter(Boolean)
}

export function hasDebugTag(tags) {
  return parseTagList(Array.isArray(tags) ? tags.join(',') : '').some(
    (tag) => tag.toLowerCase() === 'debug',
  )
}

export function applyDebugTag(tags, isDebug) {
  const unique = []
  for (const tag of tags) {
    if (!tag) continue
    const normalized = String(tag).trim()
    if (!normalized) continue
    if (!unique.some((existing) => existing.toLowerCase() === normalized.toLowerCase())) {
      unique.push(normalized)
    }
  }
  const withoutDebug = unique.filter((tag) => tag.toLowerCase() !== 'debug')
  return isDebug ? ['debug', ...withoutDebug] : withoutDebug
}

export function toErrorMessage(err, fallback) {
  return err?.response?.data?.detail || fallback
}
