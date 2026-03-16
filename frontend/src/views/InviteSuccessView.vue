<template>
  <div class="mx-auto max-w-5xl">
    <section
      class="overflow-hidden rounded-3xl border border-emerald-200 bg-gradient-to-br from-emerald-50 via-white to-sky-50 p-6 shadow-sm sm:p-10"
    >
      <div class="space-y-7">
        <div class="space-y-3">
          <p class="m-0 text-xs font-semibold uppercase tracking-[0.16em] text-emerald-700">
            National Research Platform
          </p>
          <h1 class="m-0 text-3xl font-bold text-slate-900 sm:text-4xl">Welcome to NRP</h1>
          <p class="m-0 max-w-3xl text-base leading-relaxed text-slate-700">
            Thanks for joining the National Research Platform. You now have an account with the
            National Research Platform under the account
            <span class="rounded bg-white px-2 py-1 font-mono font-semibold text-slate-900">
              {{ username || 'unknown' }}
            </span>.
          </p>
        </div>

        <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <a
            href="https://nrp.ai/documentation/"
            target="_blank"
            rel="noreferrer"
            class="block rounded-2xl border border-sky-300 bg-white p-5 no-underline shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
          >
            <p class="m-0 text-xs font-semibold uppercase tracking-wide text-sky-700">Documentation</p>
            <p class="m-0 mt-2 text-xl font-semibold text-slate-900">NRP Documentation Home</p>
            <p class="m-0 mt-2 text-sm text-slate-600">https://nrp.ai/documentation/</p>
          </a>

          <a
            href="https://nrp.ai/documentation/userdocs/start/getting-started/"
            target="_blank"
            rel="noreferrer"
            class="block rounded-2xl border border-sky-300 bg-white p-5 no-underline shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
          >
            <p class="m-0 text-xs font-semibold uppercase tracking-wide text-sky-700">Getting Started</p>
            <p class="m-0 mt-2 text-xl font-semibold text-slate-900">New User Setup Guide</p>
            <p class="m-0 mt-2 text-sm text-slate-600">
              https://nrp.ai/documentation/userdocs/start/getting-started/
            </p>
          </a>

          <a
            href="https://nrp.ai/documentation/userdocs/tutorial/introduction/"
            target="_blank"
            rel="noreferrer"
            class="block rounded-2xl border border-emerald-300 bg-white p-5 no-underline shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
          >
            <p class="m-0 text-xs font-semibold uppercase tracking-wide text-emerald-700">Tutorials</p>
            <p class="m-0 mt-2 text-xl font-semibold text-slate-900">Introduction Tutorial</p>
            <p class="m-0 mt-2 text-sm text-slate-600">
              https://nrp.ai/documentation/userdocs/tutorial/introduction/
            </p>
          </a>

          <a
            href="https://nrp.ai/training/"
            target="_blank"
            rel="noreferrer"
            class="block rounded-2xl border border-emerald-300 bg-white p-5 no-underline shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
          >
            <p class="m-0 text-xs font-semibold uppercase tracking-wide text-emerald-700">Training</p>
            <p class="m-0 mt-2 text-xl font-semibold text-slate-900">Office Hours and Trainings</p>
            <p class="m-0 mt-2 text-sm text-slate-600">https://nrp.ai/training/</p>
          </a>
        </div>

        <div class="flex flex-wrap gap-3">
          <a href="https://nrp.ai/" target="_blank" rel="noreferrer" class="no-underline">
            <Button label="Go to NRP Home" icon="pi pi-home" class="!text-base" />
          </a>
          <a href="https://nrp.ai/documentation/" target="_blank" rel="noreferrer" class="no-underline">
            <Button
              label="Open Documentation"
              icon="pi pi-book"
              severity="secondary"
              outlined
              class="!text-base"
            />
          </a>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Button from 'primevue/button'

const route = useRoute()
const username = computed(() => String(route.query.username || '').trim())
</script>
