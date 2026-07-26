import { Routes, Route, NavLink } from 'react-router-dom'
import ChatPage from './pages/ChatPage'
import DocumentsPage from './pages/DocumentsPage'
import EvalPage from './pages/EvalPage'
import './App.css'

export default function App() {
  return (
    <div className="app">
      <header className="header">
        <div className="header-brand">
          <span className="logo-mark">L</span>
          <span className="logo-text">Laya Healthcare</span>
          <span className="logo-sub">Knowledge Base</span>
        </div>
        <nav>
          <NavLink to="/" end className={({ isActive }) => isActive ? 'active' : ''}>Chat</NavLink>
          <NavLink to="/documents" className={({ isActive }) => isActive ? 'active' : ''}>Documents</NavLink>
          <NavLink to="/eval" className={({ isActive }) => isActive ? 'active' : ''}>Evaluation</NavLink>
        </nav>
      </header>
      <main className="main">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/eval" element={<EvalPage />} />
        </Routes>
      </main>
    </div>
  )
}
