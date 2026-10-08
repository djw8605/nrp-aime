<template>
  <div class="space-y-2 rounded-xl border border-violet-100 bg-violet-50 p-3">
    <div class="flex items-baseline justify-between gap-2">
      <p class="m-0 text-xs uppercase tracking-wide text-violet-600">GPU Hours Used (SU)</p>
      <p class="m-0 text-xs text-violet-500">
        data through {{ formatDate(accounting.usage_through) }}
      </p>
    </div>
    <p class="m-0 text-2xl font-bold text-violet-800">
      {{ formatUnits(accounting.gpu_hours_used) }}
      <span v-if="hasAllocation" class="text-sm font-medium text-violet-600">
        / {{ formatUnits(allocated) }}
      </span>
    </p>
    <ProgressBar
      v-if="hasAllocation"
      :value="percentUsed"
      :showValue="false"
      :aria-label="`GPU hours used: ${percentOfAllocation}% of allocation`"
      style="height: 0.5rem"
    />
    <div class="grid grid-cols-2 gap-2 text-xs">
      <div>
        <p class="m-0 text-slate-500">Loaded at ACCESS</p>
        <p class="m-0 font-semibold text-emerald-700">{{ formatUnits(accounting.su_loaded) }}</p>
      </div>
      <div>
        <p class="m-0 text-slate-500">Awaiting confirmation</p>
        <p class="m-0 font-semibold text-sky-700">{{ formatUnits(accounting.su_submitted) }}</p>
      </div>
    </div>
    <div
      v-if="isOverAllocation || accounting.su_pending > 0 || accounting.failed_records > 0"
      class="flex flex-wrap gap-2"
    >
      <Tag
        v-if="isOverAllocation"
        :value="`Over allocation (${percentOfAllocation}%)`"
        severity="danger"
        rounded
      />
      <Tag
        v-if="accounting.su_pending > 0"
        :value="`${formatUnits(accounting.su_pending)} SU not yet sent`"
        severity="secondary"
        rounded
      />
      <Tag
        v-if="accounting.failed_records > 0"
        :value="`${formatUnits(accounting.su_failed)} SU failed (${accounting.failed_records} records)`"
        severity="danger"
        rounded
      />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import ProgressBar from 'primevue/progressbar'
import Tag from 'primevue/tag'

const props = defineProps({
  accounting: {
    type: Object,
    required: true,
  },
  allocated: {
    type: Number,
    default: null,
  },
})

const hasAllocation = computed(() => Number(props.allocated || 0) > 0)

// Uncapped, so over-allocation can be reported (the bar itself stays capped).
const percentOfAllocation = computed(() => {
  if (!hasAllocation.value) return 0
  const used = Number(props.accounting.gpu_hours_used || 0)
  return Math.round((used / Number(props.allocated)) * 100)
})

const percentUsed = computed(() => Math.min(100, percentOfAllocation.value))

const isOverAllocation = computed(
  () =>
    hasAllocation.value &&
    Number(props.accounting.gpu_hours_used || 0) > Number(props.allocated),
)

function formatUnits(value) {
  return Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 2 })
}

function formatDate(value) {
  if (!value) return '—'
  return new Date(`${value}T00:00:00Z`).toLocaleDateString(undefined, { timeZone: 'UTC' })
}
</script>
