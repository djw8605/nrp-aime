<template>
  <router-link
    :to="{ name: 'project-detail', params: { id: project.id } }"
    class="block no-underline"
  >
    <Card class="h-full border border-slate-200 shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg">
      <template #title>
        <p class="m-0 truncate text-lg font-semibold text-slate-800">{{ project.name }}</p>
      </template>
      <template #subtitle>
        <div class="flex items-center justify-between gap-2">
          <span class="text-xs text-slate-500">Allocation ID: {{ project.aime_allocation_id }}</span>
          <Tag
            :value="project.is_active ? 'Active' : 'Inactive'"
            :severity="project.is_active ? 'success' : 'danger'"
            rounded
          />
        </div>
      </template>
      <template #content>
        <div class="space-y-3">
          <div class="grid grid-cols-2 gap-3">
            <div class="rounded-xl bg-sky-50 p-3 text-center">
              <p class="m-0 text-xs uppercase tracking-wide text-sky-500">Service Units</p>
              <p class="m-0 text-2xl font-bold text-sky-700">
                {{ formatUsage(project.service_units_allocated) }}
              </p>
              <p class="m-0 mt-1 text-xs text-sky-600">
                remaining {{ formatUsage(project.service_units_remaining) }}
              </p>
            </div>
            <div class="rounded-xl bg-emerald-50 p-3 text-center">
              <p class="m-0 text-xs uppercase tracking-wide text-emerald-500">Allocated Resource</p>
              <p class="m-0 mt-3 break-all text-sm font-bold text-emerald-700">
                {{ project.allocated_resource || project.resource_type || '—' }}
              </p>
            </div>
          </div>
          <div class="flex items-center justify-between gap-2 text-xs">
            <span class="text-slate-500">Usage Source</span>
            <Tag
              :value="project.usage_source || 'none'"
              :severity="project.usage_source === 'usage_snapshot' ? 'info' : 'secondary'"
              rounded
            />
          </div>
          <div class="flex items-center justify-between gap-2 text-xs">
            <span class="text-slate-500">Namespace</span>
            <Tag
              :value="project.kubernetes_namespace || 'unassigned'"
              :severity="project.kubernetes_namespace ? 'contrast' : 'secondary'"
              rounded
            />
          </div>
          <div class="flex items-center justify-between gap-2 text-xs">
            <span class="text-slate-500">Provisioning</span>
            <Tag
              :value="formatProvisioningState(project.provisioning_state)"
              :severity="provisioningSeverity(project.provisioning_state)"
              rounded
            />
          </div>
          <div class="flex items-center justify-between gap-2 text-xs">
            <span class="text-slate-500">Site Project ID</span>
            <span class="font-mono text-slate-700">{{ project.site_project_id || '—' }}</span>
          </div>
          <div class="flex items-center justify-between gap-2 text-xs">
            <span class="text-slate-500">Source Site</span>
            <span class="font-mono text-slate-700">{{ project.source_site_name || '—' }}</span>
          </div>
          <div class="flex items-center justify-between gap-2 text-xs">
            <span class="text-slate-500">Resource Type</span>
            <span class="font-mono text-slate-700">{{ project.resource_type || '—' }}</span>
          </div>
        </div>
      </template>
    </Card>
  </router-link>
</template>

<script setup>
import Card from 'primevue/card'
import Tag from 'primevue/tag'

defineProps({
  project: {
    type: Object,
    required: true,
  },
})

function formatUsage(value) {
  if (value === null || value === undefined) return '—'
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return String(value)
  return numeric.toLocaleString(undefined, { maximumFractionDigits: 2 })
}

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
</script>
