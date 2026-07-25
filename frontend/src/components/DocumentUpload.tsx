import { useState, useRef } from 'react'
import { ingestDocuments } from '../api/client'
import './DocumentUpload.css'

interface Props {
  onUploaded: () => void
}

export default function DocumentUpload({ onUploaded }: Props) {
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFiles = async (files: FileList | File[]) => {
    const list = Array.from(files)
    if (list.length === 0) return
    setUploading(true)
    setMessage('')
    try {
      const { data } = await ingestDocuments(list)
      const names = data.documents.map(d => d.name).join(', ')
      setMessage(
        list.length === 1
          ? `"${data.documents[0].name}" uploaded — processing in background.`
          : `${list.length} files uploaded (${names}) — processing in background.`
      )
      onUploaded()
    } catch {
      setMessage('Upload failed. Please try again.')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files) handleFiles(e.dataTransfer.files)
  }

  return (
    <div className="upload-area">
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.txt,.md,.docx,.xlsx"
        multiple
        onChange={e => e.target.files && handleFiles(e.target.files)}
        disabled={uploading}
        id="file-input"
      />
      <label
        htmlFor="file-input"
        className={`drop-zone ${uploading ? 'disabled' : ''} ${dragOver ? 'drag-over' : ''}`}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        {uploading ? (
          <span>Uploading...</span>
        ) : (
          <>
            <span className="upload-icon">↑</span>
            <span>Click to select or drag & drop files</span>
            <span className="upload-hint">.pdf, .docx, .xlsx, .txt, .md — multiple files supported</span>
          </>
        )}
      </label>
      {message && <p className="upload-message">{message}</p>}
    </div>
  )
}
