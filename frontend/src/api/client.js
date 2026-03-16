/**
 * Axios instance pre-configured for the NRP AIME API.
 */
import axios from 'axios'

const apiClient = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
})

export default apiClient
