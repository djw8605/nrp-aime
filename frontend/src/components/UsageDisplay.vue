<template>
  <Card class="border border-slate-200 shadow-sm">
    <template #content>
      <div v-if="loading" class="space-y-3 p-2">
        <Skeleton height="1.5rem" />
        <Skeleton height="0.75rem" />
        <Skeleton height="1.5rem" />
        <Skeleton height="0.75rem" />
      </div>
      <Message v-else-if="!usage" severity="warn" :closable="false">
        Usage data unavailable.
      </Message>
      <div v-else class="space-y-6">
        <div class="space-y-2">
          <div class="flex items-center justify-between text-sm">
            <span class="font-medium text-slate-700">CPU</span>
            <span class="text-slate-500">{{ usage.cpu_used }} / {{ usage.cpu_allocated }} cores</span>
          </div>
          <ProgressBar :value="cpuPercent" :showValue="false" style="height: 0.55rem" />
          <p class="m-0 text-right text-xs text-slate-500">{{ cpuPercent }}% used</p>
        </div>

        <div class="space-y-2">
          <div class="flex items-center justify-between text-sm">
            <span class="font-medium text-slate-700">GPU</span>
            <span class="text-slate-500">{{ usage.gpu_used }} / {{ usage.gpu_allocated }}</span>
          </div>
          <ProgressBar :value="gpuPercent" :showValue="false" style="height: 0.55rem" />
          <p class="m-0 text-right text-xs text-slate-500">{{ gpuPercent }}% used</p>
        </div>
      </div>
    </template>
  </Card>
</template>

<script setup>
import { computed } from 'vue'
import Card from 'primevue/card'
import Message from 'primevue/message'
import ProgressBar from 'primevue/progressbar'
import Skeleton from 'primevue/skeleton'

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
