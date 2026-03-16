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
        </div>
      </div>
    </template>
    <template #content>
      <Divider />
      <div class="grid grid-cols-1 gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div class="rounded-lg bg-slate-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Resource Type</p>
          <p class="m-0 mt-2 font-medium text-slate-700">{{ project.resource_type || '—' }}</p>
        </div>
        <div class="rounded-lg bg-slate-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">Grant Number</p>
          <p class="m-0 mt-2 font-medium text-slate-700">{{ project.grant_number || '—' }}</p>
        </div>
        <div class="rounded-lg bg-slate-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">CPU Cores</p>
          <p class="m-0 mt-2 font-medium text-slate-700">{{ project.cpu_allocated }}</p>
        </div>
        <div class="rounded-lg bg-slate-50 p-3">
          <p class="m-0 text-xs uppercase tracking-wide text-slate-500">GPUs</p>
          <p class="m-0 mt-2 font-medium text-slate-700">{{ project.gpu_allocated }}</p>
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
      </div>
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
</script>
