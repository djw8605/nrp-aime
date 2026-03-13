<template>
  <div class="bg-white rounded-xl shadow border border-gray-100 p-6">
    <div v-if="loading" class="text-center text-gray-400 py-4">Loading usage…</div>
    <div v-else-if="!usage" class="text-center text-gray-400 py-4">
      Usage data unavailable.
    </div>
    <div v-else class="space-y-5">
      <!-- CPU -->
      <div>
        <div class="flex justify-between text-sm mb-1">
          <span class="font-medium text-gray-700">CPU</span>
          <span class="text-gray-500">{{ usage.cpu_used }} / {{ usage.cpu_allocated }} cores</span>
        </div>
        <div class="w-full bg-gray-100 rounded-full h-3">
          <div
            class="bg-blue-500 h-3 rounded-full transition-all"
            :style="{ width: cpuPercent + '%' }"
          ></div>
        </div>
        <p class="text-xs text-gray-400 mt-1 text-right">{{ cpuPercent }}% used</p>
      </div>

      <!-- GPU -->
      <div>
        <div class="flex justify-between text-sm mb-1">
          <span class="font-medium text-gray-700">GPU</span>
          <span class="text-gray-500">{{ usage.gpu_used }} / {{ usage.gpu_allocated }}</span>
        </div>
        <div class="w-full bg-gray-100 rounded-full h-3">
          <div
            class="bg-purple-500 h-3 rounded-full transition-all"
            :style="{ width: gpuPercent + '%' }"
          ></div>
        </div>
        <p class="text-xs text-gray-400 mt-1 text-right">{{ gpuPercent }}% used</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  usage: {
    type: Object,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
})

const cpuPercent = computed(() => {
  if (!props.usage || props.usage.cpu_allocated === 0) return 0
  return Math.min(100, Math.round((props.usage.cpu_used / props.usage.cpu_allocated) * 100))
})

const gpuPercent = computed(() => {
  if (!props.usage || props.usage.gpu_allocated === 0) return 0
  return Math.min(100, Math.round((props.usage.gpu_used / props.usage.gpu_allocated) * 100))
})
</script>
