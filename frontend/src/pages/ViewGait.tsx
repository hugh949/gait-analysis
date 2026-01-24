import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Trash2, RefreshCw } from 'lucide-react'
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
  const [deletingId, setDeletingId] = useState<string | null>(null)

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
      case 'deleted':
        return 'status-deleted'
      default:
        return 'status-unknown'
    }
  }

  const handleDelete = async (analysisId: string, filename?: string) => {
    if (!window.confirm(`Are you sure you want to delete "${filename || analysisId}"? This action cannot be undone.`)) {
      return
    }

    setDeletingId(analysisId)
    try {
      const response = await fetch(`${API_URL}/api/v1/analysis/${analysisId}`, {
        method: 'DELETE',
        headers: {
          'Accept': 'application/json',
        },
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ message: 'Failed to delete analysis' }))
        throw new Error(errorData.message || `Failed to delete: ${response.statusText}`)
      }

      // Remove from local state
      setAnalyses(analyses.filter(a => a.id !== analysisId))
    } catch (err: any) {
      console.error('Error deleting analysis:', err)
      alert(`Failed to delete analysis: ${err.message || 'Unknown error'}`)
    } finally {
      setDeletingId(null)
    }
  }

  const handleRefresh = () => {
    setLoading(true)
    setError(null)
    fetch(`${API_URL}/api/v1/analysis/list`)
      .then(response => {
        if (!response.ok) {
          throw new Error(`Failed to fetch analyses: ${response.statusText}`)
        }
        return response.json()
      })
      .then(data => {
        setAnalyses(data.analyses || [])
      })
      .catch(err => {
        console.error('Error fetching analyses:', err)
        setError(err.message || 'Failed to load analyses')
      })
      .finally(() => {
        setLoading(false)
      })
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

      <div className="page-controls">
        <button 
          onClick={handleRefresh} 
          className="btn btn-secondary"
          disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
        >
          <RefreshCw size={16} className={loading ? 'spinning' : ''} />
          Refresh
        </button>
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
          {analyses
            .filter(analysis => analysis.status !== 'deleted')
            .sort((a, b) => {
              // Sort by created_at descending (newest first)
              const dateA = a.created_at ? new Date(a.created_at).getTime() : 0
              const dateB = b.created_at ? new Date(b.created_at).getTime() : 0
              return dateB - dateA
            })
            .map((analysis) => (
            <div key={analysis.id} className="analysis-card">
              <div className="analysis-header">
                <div className="analysis-info">
                  <h3>{analysis.filename || 'Untitled Analysis'}</h3>
                  <p className="analysis-id">ID: {analysis.id}</p>
                  <p className="analysis-date">Created: {formatDate(analysis.created_at)}</p>
                  {analysis.updated_at && analysis.updated_at !== analysis.created_at && (
                    <p className="analysis-date">Updated: {formatDate(analysis.updated_at)}</p>
                  )}
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
                <button
                  onClick={() => handleDelete(analysis.id, analysis.filename)}
                  className="btn btn-danger"
                  disabled={deletingId === analysis.id}
                  title="Delete this analysis"
                  style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '0.5rem',
                    backgroundColor: '#dc3545',
                    color: 'white',
                    border: 'none'
                  }}
                >
                  <Trash2 size={16} />
                  {deletingId === analysis.id ? 'Deleting...' : 'Delete'}
                </button>
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

