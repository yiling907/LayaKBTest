import axios from 'axios'

export const api = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE_URL || '') + '/api',
})

export interface QueryResponse {
  answer: string
  sources: { document: string; chunk: string }[]
}

export interface IngestResponse {
  id: string
  name: string
  chunks: number
  status: string
}

export interface Document {
  id: string
  name: string
  size: number
  status: string
  chunks: number
  _ts: number
}

export const healthCheck = () => api.get<{ status: string }>('/health')

export interface UserSummary {
  id: string
  name: string
  email: string
  age: number
  active_policies: { policy_number: string; product: string; type: string }[]
  open_claims: number
}

export const queryKB = (question: string, user_id?: string) =>
  api.post<QueryResponse>('/query', { question, user_id: user_id || null })

export const listUsers = () =>
  api.get<{ users: UserSummary[] }>('/users')

export const getUser = (id: string) =>
  api.get<Record<string, unknown>>(`/users/${id}`)

export const ingestDocument = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post<IngestResponse>('/ingest', form)
}

export const ingestDocuments = (files: File[]) => {
  const form = new FormData()
  files.forEach(f => form.append('files', f))
  return api.post<{ documents: IngestResponse[] }>('/ingest/batch', form)
}

export const listDocuments = () =>
  api.get<{ documents: Document[] }>('/documents')

export const deleteDocument = (id: string) =>
  api.delete<{ deleted: string }>(`/documents/${id}`)

export default api
