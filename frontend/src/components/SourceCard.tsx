import './SourceCard.css'

interface Props {
  document: string
  chunk: string
}

export default function SourceCard({ document, chunk }: Props) {
  return (
    <div className="source-card">
      <p className="source-doc">{document}</p>
      <p className="source-chunk">"{chunk}"</p>
    </div>
  )
}
