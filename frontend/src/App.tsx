import { Routes, Route, Link, NavLink } from 'react-router-dom'
import ChatPage from './pages/ChatPage'
import DocumentsPage from './pages/DocumentsPage'
import './App.css'

export default function App() {
  return (
    <div className="app">
      <header className="header">
        <Link to="/" className="logo">LayaKB</Link>
        <nav>
          <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>Chat</NavLink>
          <NavLink to="/documents" className={({ isActive }) => isActive ? 'active' : ''}>Documents</NavLink>
        </nav>
      </header>
      <main className="main">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
        </Routes>
      </main>
    </div>
  )
}
