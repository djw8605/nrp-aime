<template>
  <div class="bg-white rounded-xl shadow border border-gray-100 p-6">
    <div class="flex items-start justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-800">{{ project.name }}</h1>
        <p class="text-sm text-gray-400 mt-1">Allocation ID: {{ project.aime_allocation_id }}</p>
      </div>
      <button
        @click="$emit('send-email')"
        class="bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
      >
        Send Account Creation Email
      </button>
    </div>

    <div class="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
      <div>
        <p class="text-gray-400 text-xs uppercase tracking-wide">Resource Type</p>
        <p class="font-medium text-gray-700 mt-1">{{ project.resource_type || '—' }}</p>
      </div>
      <div>
        <p class="text-gray-400 text-xs uppercase tracking-wide">CPU Cores</p>
        <p class="font-medium text-gray-700 mt-1">{{ project.cpu_allocated }}</p>
      </div>
      <div>
        <p class="text-gray-400 text-xs uppercase tracking-wide">GPUs</p>
        <p class="font-medium text-gray-700 mt-1">{{ project.gpu_allocated }}</p>
      </div>
      <div>
        <p class="text-gray-400 text-xs uppercase tracking-wide">Namespace</p>
        <p class="font-mono text-gray-700 mt-1">{{ project.kubernetes_namespace || '—' }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  project: {
    type: Object,
    required: true,
  },
})

defineEmits(['send-email'])
</script>
