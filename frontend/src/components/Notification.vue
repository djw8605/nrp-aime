<template>
  <transition
    enter-active-class="transition ease-out duration-300"
    enter-from-class="opacity-0 translate-y-2"
    enter-to-class="opacity-100 translate-y-0"
    leave-active-class="transition ease-in duration-200"
    leave-from-class="opacity-100 translate-y-0"
    leave-to-class="opacity-0 translate-y-2"
  >
    <div
      v-if="message"
      class="fixed bottom-6 right-6 bg-green-600 text-white rounded-lg shadow-lg px-5 py-3 flex items-center gap-3 max-w-sm z-50"
    >
      <span class="text-sm">{{ message }}</span>
      <button
        @click="$emit('dismiss')"
        class="ml-auto text-white/80 hover:text-white text-lg leading-none"
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  </transition>
</template>

<script setup>
import { watch } from 'vue'

const props = defineProps({
  message: {
    type: String,
    default: null,
  },
})

const emit = defineEmits(['dismiss'])

// Auto-dismiss after 4 seconds
watch(
  () => props.message,
  (val) => {
    if (val) {
      setTimeout(() => emit('dismiss'), 4000)
    }
  },
)
</script>
