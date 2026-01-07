import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import './ViewGait.css'

const getApiUrl = () => {
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname
    if (hostname.includes('azurewebsites.net') || hostname.includes('localhost')) {
      return ''
    }
    if (hostname.includes('azurestaticapps.net')) {
      return 'https://gaitanalysisapp.azurewebsites.net'
    }
  }
  return (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000'
}

const API_URL = getApiUrl()

interface Analysis {
  id: string
  status: string
  filename?: string
  video_url?: string
  created_at?: string
  updated_at?: string
}

export default function ViewGait() {
  const navigate = useNavigate()
  const [analyses, setAnalyses] = useState<Analysis[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchAnalyses = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/analysis/list`)
        
        if (!response.ok) {
          throw new Error(`Failed to fetch analyses: ${response.statusText}`)
        }

        const data = await response.json()
        setAnalyses(data.analyses || [])
      } catch (err: any) {
        console.error('Error fetching analyses:', err)
        setError(err.message || 'Failed to load analyses')
      } finally {
        setLoading(false)
      }
    }

    fetchAnalyses()
  }, [])

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Unknown date'
    try {
      return new Date(dateString).toLocaleString()
    } catch {
      return dateString
    }
  }

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'completed':
        return 'status-completed'
      case 'processing':
        return 'status-processing'
      case 'failed':
        return 'status-failed'
      default:
        return 'status-unknown'
    }
  }

  if (loading) {
    return (
      <div className="view-gait-page">
        <div className="loading">Loading analyses...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="view-gait-page">
        <div className="error-message">
          <h2>Error</h2>
          <p>{error}</p>
          <button onClick={() => window.location.reload()} className="btn btn-primary">
            Retry
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="view-gait-page">
      <div className="page-header">
        <h1>View Gait Analyses</h1>
        <p>View all your previous gait analysis reports and associated videos.</p>
      </div>

      {analyses.length === 0 ? (
        <div className="no-analyses">
          <h2>No analyses found</h2>
          <p>You haven't uploaded any videos yet. Start by uploading a video for analysis.</p>
          <button onClick={() => navigate('/upload')} className="btn btn-primary">
            Upload Video
          </button>
        </div>
      ) : (
        <div className="analyses-list">
          {analyses.map((analysis) => (
            <div key={analysis.id} className="analysis-card">
              <div className="analysis-header">
                <div className="analysis-info">
                  <h3>{analysis.filename || 'Untitled Analysis'}</h3>
                  <p className="analysis-id">ID: {analysis.id}</p>
                  <p className="analysis-date">Created: {formatDate(analysis.created_at)}</p>
                </div>
                <div className={`status-badge ${getStatusBadgeClass(analysis.status)}`}>
                  {analysis.status}
                </div>
              </div>

              <div className="analysis-actions">
                {analysis.status === 'completed' && (
                  <button
                    onClick={() => navigate(`/report/${analysis.id}`)}
                    className="btn btn-primary"
                  >
                    View Report
                  </button>
                )}
                {analysis.video_url && (
                  <a
                    href={analysis.video_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn btn-secondary"
                  >
                    View Video
                  </a>
                )}
                {analysis.status === 'processing' && (
                  <span className="processing-note">Analysis in progress...</span>
                )}
                {analysis.status === 'failed' && (
                  <span className="failed-note">Analysis failed. Please try uploading again.</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="page-actions">
        <button onClick={() => navigate('/upload')} className="btn btn-primary">
          Upload New Video
        </button>
      </div>
    </div>
  )
}

