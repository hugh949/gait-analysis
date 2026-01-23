import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import './Layout.css'

interface LayoutProps {
  children: ReactNode
  selectedAudience?: string
  setSelectedAudience?: (audience: string) => void
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()

  return (
    <div className="layout">
      <header className="header">
        <div className="header-content">
          <h1>Gait Analysis Platform</h1>
          <nav className="nav">
            <Link 
              to="/upload" 
              className={location.pathname === '/upload' ? 'active' : ''}
            >
              Upload Video
            </Link>
            <Link 
              to="/view-reports" 
              className={location.pathname === '/view-reports' || location.pathname.startsWith('/report/') ? 'active' : ''}
            >
              View Reports
            </Link>
          </nav>
        </div>
      </header>
      <main className="main-content">
        {children}
      </main>
      <footer className="footer">
        <p>Gait Analysis Platform - Clinical-Grade Mobility Monitoring</p>
      </footer>
    </div>
  )
}

