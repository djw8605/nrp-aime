<template>
  <router-link
    :to="{ name: 'project-detail', params: { id: project.id } }"
    class="block bg-white rounded-xl shadow hover:shadow-md transition-shadow border border-gray-100 p-5"
  >
    <h2 class="text-lg font-semibold text-gray-800 mb-1 truncate">{{ project.name }}</h2>
    <p class="text-xs text-gray-400 mb-4 truncate">ID: {{ project.aime_allocation_id }}</p>

    <div class="flex gap-4 text-sm text-gray-600">
      <div class="flex-1 bg-blue-50 rounded-lg p-3 text-center">
        <p class="text-xs text-blue-400 uppercase tracking-wide font-medium">CPU Cores</p>
        <p class="text-2xl font-bold text-blue-700">{{ project.cpu_allocated }}</p>
      </div>
      <div class="flex-1 bg-purple-50 rounded-lg p-3 text-center">
        <p class="text-xs text-purple-400 uppercase tracking-wide font-medium">GPUs</p>
        <p class="text-2xl font-bold text-purple-700">{{ project.gpu_allocated }}</p>
      </div>
    </div>

    <p v-if="project.kubernetes_namespace" class="mt-3 text-xs text-gray-400">
      Namespace: <span class="font-mono">{{ project.kubernetes_namespace }}</span>
    </p>
  </router-link>
</template>

<script setup>
defineProps({
  project: {
    type: Object,
    required: true,
  },
})
</script>
