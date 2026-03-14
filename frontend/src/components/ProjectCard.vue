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
              <p class="m-0 text-xs uppercase tracking-wide text-sky-500">CPU Cores</p>
              <p class="m-0 text-2xl font-bold text-sky-700">{{ project.cpu_allocated }}</p>
            </div>
            <div class="rounded-xl bg-emerald-50 p-3 text-center">
              <p class="m-0 text-xs uppercase tracking-wide text-emerald-500">GPUs</p>
              <p class="m-0 text-2xl font-bold text-emerald-700">{{ project.gpu_allocated }}</p>
            </div>
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
            <span class="text-slate-500">Site Project ID</span>
            <span class="font-mono text-slate-700">{{ project.site_project_id || '—' }}</span>
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
</script>
