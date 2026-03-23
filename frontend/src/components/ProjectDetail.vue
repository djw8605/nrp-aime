<template>
  <Card class="border border-slate-200 shadow-sm">
    <template #title>
      <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div class="flex flex-wrap items-center gap-2">
            <h1 class="m-0 text-2xl font-bold text-slate-800">{{ project.name }}</h1>
            <Tag
              :value="project.is_active ? 'Active' : 'Inactive'"
              :severity="project.is_active ? 'success' : 'danger'"
              rounded
            />
          </div>
          <p class="m-0 mt-1 text-sm text-slate-500">
            Allocation ID: {{ project.aime_allocation_id }}
          </p>
          <div v-if="(project.tags || []).length" class="mt-2 flex flex-wrap gap-2">
            <Tag
              v-for="tag in project.tags"
              :key="tag"
              :value="tag"
              severity="contrast"
              rounded
            />
          </div>
        </div>
      </div>
    </template>
    <template #content>
      <Divider />
      <div class="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div class="rounded-lg bg-sky-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-sky-600">Service Units Allocated</p>
          <p class="m-0 mt-2 text-xl font-semibold text-sky-800">
            {{ formatUnits(project.service_units_allocated) }}
          </p>
        </div>
        <div class="rounded-lg bg-emerald-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-emerald-600">Service Units Remaining</p>
          <p class="m-0 mt-2 text-xl font-semibold text-emerald-800">
            {{ formatUnits(project.service_units_remaining) }}
          </p>
        </div>
        <div class="rounded-lg bg-indigo-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-indigo-600">Allocated Resource</p>
          <p class="m-0 mt-2 break-all font-medium text-indigo-800">
            {{ project.allocated_resource || '—' }}
          </p>
        </div>
        <div class="rounded-lg bg-slate-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Resource Type</p>
          <p class="m-0 mt-2 font-medium text-slate-700">{{ project.resource_type || '—' }}</p>
        </div>
        <div class="rounded-lg bg-slate-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Grant Number</p>
          <p class="m-0 mt-2 font-medium text-slate-700">{{ project.grant_number || '—' }}</p>
        </div>
        <div class="rounded-lg bg-slate-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Site Project ID</p>
          <p class="m-0 mt-2 font-mono font-medium text-slate-700">
            {{ project.site_project_id || '—' }}
          </p>
        </div>
        <div class="rounded-lg bg-slate-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Allocation Type</p>
          <p class="m-0 mt-2 font-medium text-slate-700">{{ project.allocation_type || '—' }}</p>
        </div>
        <div class="rounded-lg bg-slate-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Request Type</p>
          <p class="m-0 mt-2 font-medium text-slate-700">{{ project.request_type || '—' }}</p>
        </div>
        <div class="rounded-lg bg-slate-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Namespace</p>
          <p class="m-0 mt-2 font-mono font-medium text-slate-700">
            {{ project.kubernetes_namespace || '—' }}
          </p>
        </div>
        <div class="rounded-lg bg-slate-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Provisioning State</p>
          <Tag
            class="mt-2"
            :value="formatProvisioningState(project.provisioning_state)"
            :severity="provisioningSeverity(project.provisioning_state)"
            rounded
          />
        </div>
        <div class="rounded-lg bg-slate-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Authentik Group</p>
          <p class="m-0 mt-2 font-mono font-medium text-slate-700">
            {{ project.authentik_group_name || '—' }}
          </p>
        </div>
        <div class="rounded-lg bg-slate-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Source Site</p>
          <p class="m-0 mt-2 font-mono font-medium text-slate-700">
            {{ project.source_site_name || '—' }}
          </p>
        </div>
        <div class="rounded-lg bg-slate-50 p-3 sm:col-span-2 lg:col-span-4">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Custom Tags</p>
          <div v-if="!(project.tags || []).length" class="mt-2 text-sm font-medium text-slate-700">
            No custom tags set.
          </div>
          <div v-else class="mt-2 flex flex-wrap gap-2">
            <Tag
              v-for="tag in project.tags"
              :key="tag"
              :value="tag"
              severity="contrast"
              rounded
            />
          </div>
        </div>
      </div>
      <p
        v-if="project.provisioning_last_error"
        class="m-0 mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800"
      >
        {{ project.provisioning_last_error }}
      </p>
    </template>
  </Card>
</template>

<script setup>
import Card from 'primevue/card'
import Divider from 'primevue/divider'
import Tag from 'primevue/tag'

defineProps({
  project: {
    type: Object,
    required: true,
  },
})

function formatProvisioningState(value) {
  const state = String(value || 'received').trim().toLowerCase()
  if (state === 'received') return 'Received'
  if (state === 'provisioning') return 'Provisioning'
  if (state === 'ready') return 'Ready'
  if (state === 'failed') return 'Failed'
  return state || 'Unknown'
}

function provisioningSeverity(value) {
  const state = String(value || 'received').trim().toLowerCase()
  if (state === 'ready') return 'success'
  if (state === 'provisioning') return 'warning'
  if (state === 'failed') return 'danger'
  return 'info'
}

function formatUnits(value) {
  if (value === null || value === undefined) return '—'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 4 })
}
</script>
