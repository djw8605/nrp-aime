import { createRouter, createWebHistory } from 'vue-router'
import ProjectsView from '../views/ProjectsView.vue'
import ProjectDetailView from '../views/ProjectDetailView.vue'
import PacketLogsView from '../views/PacketLogsView.vue'

const routes = [
  {
    path: '/',
    name: 'projects',
    component: ProjectsView,
  },
  {
    path: '/projects/:id',
    name: 'project-detail',
    component: ProjectDetailView,
    props: true,
  },
  {
    path: '/packets/logs',
    name: 'packet-logs',
    component: PacketLogsView,
  },
  {
    path: '/packets/unprocessed',
    redirect: { name: 'packet-logs' },
  },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
