import { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import './Layout.css'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const location = useLocation()
  const isHome = location.pathname === '/'
  const isReports = location.pathname === '/reports' || location.pathname.startsWith('/report/')

  return (
    <div className="layout">
      <header className="header">
        <div className="header-content">
          <h1>Gait Analysis Platform</h1>
          <nav className="nav">
            <Link 
              to="/" 
              className={isHome ? 'active' : ''}
            >
              New Analysis
            </Link>
            <Link 
              to="/reports" 
              className={isReports ? 'active' : ''}
            >
              View Reports
            </Link>
          </nav>
        </div>
      </header>
      <main className="main-content">
        {children}
      </main>
    </div>
  )
}

