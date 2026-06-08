import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

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

export const queryKB = (question: string) =>
  api.post<QueryResponse>('/query', { question })

export const ingestDocument = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return api.post<IngestResponse>('/ingest', form)
}

export const listDocuments = () =>
  api.get<{ documents: Document[] }>('/documents')
