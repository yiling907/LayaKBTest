import { useState, useRef } from 'react'
import { ingestDocument } from '../api/client'
import './DocumentUpload.css'

interface Props {
  onUploaded: () => void
}

export default function DocumentUpload({ onUploaded }: Props) {
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFile = async (file: File) => {
    setUploading(true)
    setMessage('')
    try {
      const { data } = await ingestDocument(file)
      setMessage(`"${data.name}" indexed successfully (${data.chunks} chunks).`)
      onUploaded()
    } catch {
      setMessage('Upload failed. Please try again.')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div className="upload-area">
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.txt,.md"
        onChange={e => e.target.files?.[0] && handleFile(e.target.files[0])}
        disabled={uploading}
        id="file-input"
      />
      <label htmlFor="file-input" className={uploading ? 'disabled' : ''}>
        {uploading ? 'Uploading...' : 'Choose file to upload (.pdf, .txt, .md)'}
      </label>
      {message && <p className="upload-message">{message}</p>}
    </div>
  )
}
