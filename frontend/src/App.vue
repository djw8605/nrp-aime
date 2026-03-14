<template>
  <div class="min-h-screen">
    <Toolbar class="!rounded-none border-0 border-b border-slate-200 bg-white/90 backdrop-blur">
      <template #start>
        <router-link to="/" class="flex items-center gap-3 text-slate-800 no-underline">
          <span class="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-sky-600 text-white">
            <i class="pi pi-server text-sm"></i>
          </span>
          <div class="leading-tight">
            <p class="m-0 text-xs uppercase tracking-wide text-slate-500">National Research Platform</p>
            <p class="m-0 text-base font-semibold">AIME Allocation Manager</p>
          </div>
        </router-link>
      </template>
      <template #end>
        <div class="flex items-center gap-2">
          <router-link to="/" class="no-underline">
            <Button label="Projects" size="small" text />
          </router-link>
          <router-link :to="{ name: 'packet-logs' }" class="no-underline">
            <Button
              label="Packet Log"
              icon="pi pi-list-check"
              size="small"
              severity="contrast"
              outlined
            />
          </router-link>
          <Tag severity="info" value="PrimeVue + Tailwind" rounded />
        </div>
      </template>
    </Toolbar>

    <main class="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import Toolbar from 'primevue/toolbar'
</script>
