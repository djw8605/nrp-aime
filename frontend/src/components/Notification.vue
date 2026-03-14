<template>
  <Message
    v-if="message"
    severity="success"
    closable
    class="fixed bottom-6 right-6 z-50 w-[26rem] max-w-[92vw] shadow-xl"
    @close="$emit('dismiss')"
  >
    {{ message }}
  </Message>
</template>

<script setup>
import { watch } from 'vue'
import Message from 'primevue/message'

const props = defineProps({
  message: {
    type: String,
    default: null,
  },
})

const emit = defineEmits(['dismiss'])
let timerId = null

watch(
  () => props.message,
  (value) => {
    if (timerId) {
      clearTimeout(timerId)
      timerId = null
    }

    if (value) {
      timerId = setTimeout(() => {
        emit('dismiss')
        timerId = null
      }, 4000)
    }
  },
)
</script>
