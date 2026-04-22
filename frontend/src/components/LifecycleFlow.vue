<template>
  <div>
    <div v-for="(step, idx) in steps" :key="idx" class="relative flex gap-3">
      <!-- Left: icon circle + connector line -->
      <div class="flex flex-col items-center">
        <div
          :class="[
            'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs ring-2',
            circleClass(step.status),
          ]"
        >
          <i v-if="step.status === 'completed'" class="pi pi-check text-xs"></i>
          <i v-else-if="step.status === 'error'" class="pi pi-times text-xs"></i>
          <i v-else-if="step.status === 'active'" class="pi pi-spin pi-spinner text-xs"></i>
          <i v-else-if="step.status === 'waiting'" class="pi pi-exclamation-triangle text-xs"></i>
          <span v-else class="text-xs font-semibold">{{ idx + 1 }}</span>
        </div>
        <div
          v-if="idx < steps.length - 1"
          class="my-0.5 w-0.5 flex-1 bg-slate-200"
          style="min-height: 1.25rem"
        ></div>
      </div>

      <!-- Right: step content -->
      <div class="min-w-0 pb-4 pt-1">
        <div class="flex flex-wrap items-center gap-2">
          <span :class="['text-sm font-semibold leading-tight', labelClass(step.status)]">
            {{ step.label }}
          </span>
          <Tag
            v-if="step.status === 'waiting'"
            value="Action Required"
            severity="warn"
            rounded
          />
          <Tag
            v-else-if="step.status === 'active'"
            value="In Progress"
            severity="info"
            rounded
          />
          <Tag
            v-else-if="step.status === 'error'"
            value="Failed"
            severity="danger"
            rounded
          />
          <span v-if="step.timestamp" class="text-xs text-slate-400">
            {{ formatDate(step.timestamp) }}
          </span>
        </div>
        <p v-if="step.description" class="m-0 mt-0.5 text-xs text-slate-500">
          {{ step.description }}
        </p>
        <div
          v-if="step.actionRequired"
          class="mt-1.5 flex items-start gap-1.5 rounded-md border border-amber-200 bg-amber-50 px-2.5 py-1.5"
        >
          <i class="pi pi-info-circle mt-0.5 shrink-0 text-xs text-amber-600"></i>
          <p class="m-0 text-xs font-medium text-amber-800">{{ step.actionRequired }}</p>
        </div>
        <div v-if="step.actions?.length" class="mt-2 flex flex-wrap items-center gap-2">
          <Button
            v-for="action in step.actions"
            :key="action.key || action.label"
            :icon="action.icon"
            :label="action.label"
            :severity="action.severity || 'contrast'"
            :outlined="Boolean(action.outlined)"
            size="small"
            :loading="Boolean(action.loading)"
            :disabled="Boolean(action.disabled)"
            @click="action.onClick?.()"
          />
        </div>
        <router-link
          v-if="step.link"
          :to="step.link.to"
          class="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-sky-600 no-underline hover:underline"
        >
          {{ step.link.label }}
          <i class="pi pi-arrow-right text-xs"></i>
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import Button from 'primevue/button'
import Tag from 'primevue/tag'

defineProps({
  steps: {
    type: Array,
    required: true,
  },
})

function circleClass(status) {
  if (status === 'completed') return 'bg-emerald-100 text-emerald-700 ring-emerald-300'
  if (status === 'error') return 'bg-rose-100 text-rose-700 ring-rose-300'
  if (status === 'active') return 'bg-sky-100 text-sky-700 ring-sky-300'
  if (status === 'waiting') return 'bg-amber-100 text-amber-700 ring-amber-300'
  return 'bg-slate-100 text-slate-400 ring-slate-200'
}

function labelClass(status) {
  if (status === 'completed') return 'text-slate-800'
  if (status === 'error') return 'text-rose-700'
  if (status === 'active') return 'text-sky-700'
  if (status === 'waiting') return 'text-amber-700'
  return 'text-slate-400'
}

function formatDate(value) {
  if (!value) return ''
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}
</script>
