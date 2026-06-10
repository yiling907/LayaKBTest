import { useState, useEffect } from 'react'
import { listDocuments, Document } from '../api/client'
import DocumentUpload from '../components/DocumentUpload'
import './DocumentsPage.css'

export default function DocumentsPage() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)

  const fetchDocuments = async () => {
    try {
      const { data } = await listDocuments()
      setDocuments(data.documents)
    } catch {
      // ignore — empty list on error
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchDocuments() }, [])

  return (
    <div className="documents-page">
      <h1>Documents</h1>
      <DocumentUpload onUploaded={fetchDocuments} />

      <section className="doc-list">
        <h2>Indexed documents</h2>
        {loading ? (
          <p className="status-text">Loading...</p>
        ) : documents.length === 0 ? (
          <p className="status-text">No documents yet. Upload one above.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Chunks</th>
                <th>Status</th>
                <th>Size</th>
              </tr>
            </thead>
            <tbody>
              {documents.map(doc => (
                <tr key={doc.id}>
                  <td>{doc.name}</td>
                  <td>{doc.chunks}</td>
                  <td><span className={`badge ${doc.status}`}>{doc.status}</span></td>
                  <td>{(doc.size / 1024).toFixed(1)} KB</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
