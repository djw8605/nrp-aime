<template>
  <div class="space-y-5">
    <div class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h1 class="m-0 text-3xl font-bold tracking-tight text-slate-800">Manual Packet Input</h1>
        <p class="m-0 mt-1 text-sm text-slate-500">
          Manually enter packet details and ingest them into the database.
        </p>
      </div>
      <div class="flex gap-2">
        <router-link :to="{ name: 'packet-logs' }" class="no-underline">
          <Button label="Back To Packet Log" icon="pi pi-arrow-left" severity="secondary" />
        </router-link>
        <Button
          icon="pi pi-refresh"
          label="Reload Prefill"
          severity="secondary"
          outlined
          :disabled="!packetIdQuery || prefillLoading"
          :loading="prefillLoading"
          @click="loadPrefill(packetIdQuery)"
        />
      </div>
    </div>

    <Message v-if="errorMessage" severity="error" :closable="false">
      {{ errorMessage }}
    </Message>
    <Message v-if="successMessage" severity="success" :closable="false">
      {{ successMessage }}
    </Message>
    <Message v-if="validationMessage" severity="info" :closable="false">
      {{ validationMessage }}
    </Message>

    <Card v-if="sourcePacket" class="border border-slate-200/80 shadow-sm">
      <template #title>Source Packet (From Log)</template>
      <template #content>
        <div class="grid grid-cols-1 gap-3 text-sm md:grid-cols-3">
          <p class="m-0"><strong>Type:</strong> {{ sourcePacket.packet_type }}</p>
          <p class="m-0"><strong>Packet Rec ID:</strong> {{ sourcePacket.packet_rec_id }}</p>
          <p class="m-0"><strong>Status:</strong> {{ sourcePacket.processing_status }}</p>
        </div>
        <div class="mt-3 rounded-lg border border-slate-200 bg-slate-950 p-3">
          <pre class="m-0 max-h-[22rem] overflow-auto text-xs leading-relaxed text-slate-100">{{ prettyJson(sourcePacket.raw_packet) }}</pre>
        </div>
      </template>
    </Card>

    <Card class="border border-slate-200/80 shadow-sm">
      <template #title>Packet Fields</template>
      <template #content>
        <form class="space-y-4" @submit.prevent="submitPacket">
          <div class="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            <div class="field">
              <label class="mb-1 block text-sm font-medium text-slate-700">Packet Type</label>
              <InputText v-model.trim="form.packet_type" placeholder="request_project_create" required />
            </div>
            <div class="field">
              <label class="mb-1 block text-sm font-medium text-slate-700">Packet Rec ID</label>
              <InputText v-model.trim="form.packet_rec_id" placeholder="12345" required />
            </div>
            <div class="field">
              <label class="mb-1 block text-sm font-medium text-slate-700">Trans Rec ID</label>
              <InputText v-model.trim="form.trans_rec_id" placeholder="optional" />
            </div>
            <div class="field">
              <label class="mb-1 block text-sm font-medium text-slate-700">Packet ID</label>
              <InputText v-model.trim="form.packet_id" placeholder="optional" />
            </div>
            <div class="field">
              <label class="mb-1 block text-sm font-medium text-slate-700">Transaction ID</label>
              <InputText v-model.trim="form.transaction_id" placeholder="optional" />
            </div>
            <div class="field">
              <label class="mb-1 block text-sm font-medium text-slate-700">Packet Timestamp (ISO 8601)</label>
              <InputText v-model.trim="form.packet_timestamp" placeholder="2026-03-15T01:23:45Z" />
            </div>
            <div class="field">
              <label class="mb-1 block text-sm font-medium text-slate-700">Local Site Name</label>
              <InputText v-model.trim="form.local_site_name" placeholder="NRP" />
            </div>
            <div class="field">
              <label class="mb-1 block text-sm font-medium text-slate-700">Remote Site Name</label>
              <InputText v-model.trim="form.remote_site_name" placeholder="optional" />
            </div>
            <div class="field">
              <label class="mb-1 block text-sm font-medium text-slate-700">Originating Site Name</label>
              <InputText v-model.trim="form.originating_site_name" placeholder="optional" />
            </div>
            <div class="field">
              <label class="mb-1 block text-sm font-medium text-slate-700">Transaction State</label>
              <InputText v-model.trim="form.transaction_state" placeholder="optional" />
            </div>
            <div class="field">
              <label class="mb-1 block text-sm font-medium text-slate-700">Packet State</label>
              <InputText v-model.trim="form.packet_state" placeholder="optional" />
            </div>
            <div class="field">
              <label class="mb-1 block text-sm font-medium text-slate-700">Client State</label>
              <InputText v-model.trim="form.client_state" placeholder="optional" />
            </div>
          </div>

          <div class="flex items-center gap-2">
            <Checkbox v-model="form.outgoing_flag" binary inputId="outgoing_flag" />
            <label for="outgoing_flag" class="text-sm font-medium text-slate-700">Outgoing Flag</label>
          </div>

          <div>
            <label class="mb-1 block text-sm font-medium text-slate-700">Packet Body (JSON)</label>
            <Textarea
              v-model="form.body_json"
              rows="16"
              autoResize
              class="w-full font-mono text-sm"
              placeholder="{ ...packet body... }"
            />
          </div>

          <div class="flex flex-wrap gap-2">
            <Button type="submit" label="Ingest Manual Packet" icon="pi pi-save" :loading="submitLoading" />
            <Button
              type="button"
              label="Dry-Run Validate"
              icon="pi pi-check-circle"
              severity="secondary"
              :loading="validateLoading"
              @click="handleValidatePacket"
            />
            <Button
              type="button"
              label="Reset Form"
              icon="pi pi-replay"
              severity="secondary"
              outlined
              @click="resetForm"
            />
          </div>
        </form>
      </template>
    </Card>

    <Card v-if="validationResult" class="border border-slate-200/80 shadow-sm">
      <template #title>Validation Result</template>
      <template #content>
        <div class="space-y-3">
          <p class="m-0 text-sm">
            <strong>Valid:</strong> {{ validationResult.valid ? 'Yes' : 'No' }}
          </p>
          <p class="m-0 text-sm">
            <strong>Packet Type:</strong> {{ validationResult.packet_type }}
          </p>
          <p class="m-0 text-sm">
            <strong>Binding:</strong> {{ validationResult.bound_type || '—' }}
          </p>
          <div>
            <p class="m-0 mb-1 text-sm font-semibold text-slate-700">Errors</p>
            <ul class="m-0 ml-5 text-sm text-slate-700">
              <li v-for="(entry, idx) in validationResult.errors" :key="idx">
                {{ entry.location ? `${entry.location}: ` : '' }}{{ entry.message }}
                <span v-if="entry.suggestion"> ({{ entry.suggestion }})</span>
              </li>
              <li v-if="!validationResult.errors?.length">None</li>
            </ul>
          </div>
        </div>
      </template>
    </Card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Checkbox from 'primevue/checkbox'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import Textarea from 'primevue/textarea'
import { fetchPacketLog, submitManualPacket, validatePacket } from '../api/packets'

const route = useRoute()
const prefillLoading = ref(false)
const submitLoading = ref(false)
const validateLoading = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const validationMessage = ref('')
const validationResult = ref(null)
const sourcePacket = ref(null)

const form = reactive({
  packet_type: '',
  packet_rec_id: '',
  trans_rec_id: '',
  packet_id: '',
  transaction_id: '',
  packet_timestamp: '',
  local_site_name: '',
  remote_site_name: '',
  originating_site_name: '',
  outgoing_flag: false,
  transaction_state: '',
  packet_state: '',
  client_state: '',
  body_json: '{}',
})

const packetIdQuery = computed(() => {
  const value = route.query.packetId
  return typeof value === 'string' ? value : ''
})

function prettyJson(value) {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function toStringOrEmpty(value) {
  if (value === null || value === undefined) return ''
  return String(value)
}

function applyPrefill(packet) {
  sourcePacket.value = packet
  const rawPacket = packet?.raw_packet || {}
  const header = rawPacket.header || {}
  const body = rawPacket.body || {}

  form.packet_type = rawPacket.type || packet.packet_type || ''
  form.packet_rec_id = toStringOrEmpty(header.packet_rec_id ?? packet.packet_rec_id)
  form.trans_rec_id = toStringOrEmpty(header.trans_rec_id ?? packet.trans_rec_id)
  form.packet_id = toStringOrEmpty(header.packet_id)
  form.transaction_id = toStringOrEmpty(header.transaction_id ?? packet.transaction_id)
  form.packet_timestamp = toStringOrEmpty(header.packet_timestamp)
  form.local_site_name = toStringOrEmpty(header.local_site_name)
  form.remote_site_name = toStringOrEmpty(header.remote_site_name)
  form.originating_site_name = toStringOrEmpty(header.originating_site_name)
  form.outgoing_flag = Boolean(header.outgoing_flag)
  form.transaction_state = toStringOrEmpty(header.transaction_state)
  form.packet_state = toStringOrEmpty(header.packet_state)
  form.client_state = toStringOrEmpty(header.client_state)
  form.body_json = prettyJson(body)
}

function resetForm() {
  form.packet_type = ''
  form.packet_rec_id = ''
  form.trans_rec_id = ''
  form.packet_id = ''
  form.transaction_id = ''
  form.packet_timestamp = ''
  form.local_site_name = ''
  form.remote_site_name = ''
  form.originating_site_name = ''
  form.outgoing_flag = false
  form.transaction_state = ''
  form.packet_state = ''
  form.client_state = ''
  form.body_json = '{}'
  errorMessage.value = ''
  successMessage.value = ''
  validationMessage.value = ''
  validationResult.value = null
}

async function loadPrefill(packetId) {
  if (!packetId) return
  prefillLoading.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const packet = await fetchPacketLog(packetId)
    applyPrefill(packet)
  } catch (error) {
    errorMessage.value = error?.response?.data?.detail || 'Failed to load packet prefill data.'
  } finally {
    prefillLoading.value = false
  }
}

function toOptionalInt(value) {
  const text = String(value ?? '').trim()
  if (!text) return null
  const parsed = Number.parseInt(text, 10)
  if (Number.isNaN(parsed)) {
    throw new Error(`Invalid integer value: ${text}`)
  }
  return parsed
}

function toOptionalString(value) {
  const text = String(value ?? '').trim()
  return text || null
}

async function submitPacket() {
  errorMessage.value = ''
  successMessage.value = ''
  validationMessage.value = ''
  submitLoading.value = true
  try {
    const body = JSON.parse(form.body_json || '{}')
    const packetRecId = toOptionalInt(form.packet_rec_id)
    if (packetRecId === null) {
      throw new Error('Packet Rec ID is required.')
    }

    const payload = {
      packet_type: form.packet_type.trim(),
      packet_rec_id: packetRecId,
      trans_rec_id: toOptionalInt(form.trans_rec_id),
      packet_id: toOptionalInt(form.packet_id),
      transaction_id: toOptionalInt(form.transaction_id),
      packet_timestamp: toOptionalString(form.packet_timestamp),
      local_site_name: toOptionalString(form.local_site_name),
      remote_site_name: toOptionalString(form.remote_site_name),
      originating_site_name: toOptionalString(form.originating_site_name),
      outgoing_flag: Boolean(form.outgoing_flag),
      transaction_state: toOptionalString(form.transaction_state),
      packet_state: toOptionalString(form.packet_state),
      client_state: toOptionalString(form.client_state),
      body,
    }

    const result = await submitManualPacket(payload)
    successMessage.value = `Manual packet ingested successfully (packet_rec_id=${result.packet_rec_id}, status=${result.processing_status}).`
    sourcePacket.value = result
  } catch (error) {
    errorMessage.value =
      error?.response?.data?.detail ||
      error?.message ||
      'Manual packet ingest failed.'
  } finally {
    submitLoading.value = false
  }
}

function buildRawPacketFromForm() {
  return {
    type: form.packet_type.trim(),
    header: {
      packet_rec_id: toOptionalInt(form.packet_rec_id),
      trans_rec_id: toOptionalInt(form.trans_rec_id),
      packet_id: toOptionalInt(form.packet_id),
      transaction_id: toOptionalInt(form.transaction_id),
      packet_timestamp: toOptionalString(form.packet_timestamp),
      local_site_name: toOptionalString(form.local_site_name),
      remote_site_name: toOptionalString(form.remote_site_name),
      originating_site_name: toOptionalString(form.originating_site_name),
      outgoing_flag: Boolean(form.outgoing_flag),
      transaction_state: toOptionalString(form.transaction_state),
      packet_state: toOptionalString(form.packet_state),
      client_state: toOptionalString(form.client_state),
    },
    body: JSON.parse(form.body_json || '{}'),
  }
}

async function handleValidatePacket() {
  errorMessage.value = ''
  successMessage.value = ''
  validationMessage.value = ''
  validateLoading.value = true
  try {
    const rawPacket = buildRawPacketFromForm()
    validationResult.value = await validatePacket(rawPacket)
    validationMessage.value = validationResult.value.valid
      ? 'Packet validation passed.'
      : 'Packet validation failed. See details below.'
  } catch (error) {
    errorMessage.value =
      error?.response?.data?.detail ||
      error?.message ||
      'Packet validation failed.'
  } finally {
    validateLoading.value = false
  }
}

onMounted(async () => {
  if (packetIdQuery.value) {
    await loadPrefill(packetIdQuery.value)
  }
})

watch(
  () => packetIdQuery.value,
  async (value, oldValue) => {
    if (value && value !== oldValue) {
      await loadPrefill(value)
    }
  },
)
</script>
