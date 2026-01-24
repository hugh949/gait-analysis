import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { FileText, Calendar, Trash2, RefreshCw } from 'lucide-react'
import './ViewReports.css'

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
  metrics?: {
    walking_speed?: number
    cadence?: number
    fall_risk_assessment?: {
      risk_level?: string
    }
    functional_mobility?: {
      mobility_level?: string
    }
  }
}

export default function ViewReports() {
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
        // Filter to only completed analyses and sort by latest first
        const completed = (data.analyses || [])
          .filter((a: Analysis) => a.status === 'completed')
          .sort((a: Analysis, b: Analysis) => {
            const dateA = a.updated_at || a.created_at || ''
            const dateB = b.updated_at || b.created_at || ''
            return dateB.localeCompare(dateA) // Latest first
          })
        setAnalyses(completed)
      } catch (err: any) {
        console.error('Error fetching analyses:', err)
        setError(err.message || 'Failed to load reports')
      } finally {
        setLoading(false)
      }
    }

    fetchAnalyses()
    
    // Refresh every 30 seconds to catch newly completed reports
    const interval = setInterval(fetchAnalyses, 30000)
    return () => clearInterval(interval)
  }, [])

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Unknown date'
    try {
      const date = new Date(dateString)
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return dateString
    }
  }

  const getRiskLevelColor = (riskLevel?: string) => {
    switch (riskLevel?.toLowerCase()) {
      case 'low':
        return '#2ecc71'
      case 'moderate':
        return '#f39c12'
      case 'high':
        return '#e74c3c'
      default:
        return '#95a5a6'
    }
  }

  const getMobilityLevelColor = (mobilityLevel?: string) => {
    switch (mobilityLevel?.toLowerCase()) {
      case 'excellent':
      case 'good':
        return '#2ecc71'
      case 'moderate':
        return '#f39c12'
      case 'poor':
      case 'limited':
        return '#e74c3c'
      default:
        return '#95a5a6'
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
        const completed = (data.analyses || [])
          .filter((a: Analysis) => a.status === 'completed')
          .sort((a: Analysis, b: Analysis) => {
            const dateA = a.updated_at || a.created_at || ''
            const dateB = b.updated_at || b.created_at || ''
            return dateB.localeCompare(dateA)
          })
        setAnalyses(completed)
      })
      .catch(err => {
        console.error('Error fetching analyses:', err)
        setError(err.message || 'Failed to load reports')
      })
      .finally(() => {
        setLoading(false)
      })
  }

  if (loading) {
    return (
      <div className="view-reports-page">
        <div className="loading">Loading reports...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="view-reports-page">
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
    <div className="view-reports-page">
      <div className="page-header">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <div>
            <h1>View Reports</h1>
            <p>View all your completed gait analysis reports. Latest reports appear first.</p>
          </div>
          <button 
            onClick={handleRefresh} 
            className="btn btn-secondary"
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
      </div>

      {analyses.length === 0 ? (
        <div className="no-reports">
          <FileText size={64} className="empty-icon" />
          <h2>No reports yet</h2>
          <p>You haven't completed any analyses yet. Upload a video to get started.</p>
          <button onClick={() => navigate('/')} className="btn btn-primary">
            Upload Video
          </button>
        </div>
      ) : (
        <div className="reports-list">
          {analyses.map((analysis, index) => (
            <div key={analysis.id} className={`report-card ${index === 0 ? 'latest' : ''}`}>
              {index === 0 && (
                <div className="latest-badge">Latest Report</div>
              )}
              <div className="report-header">
                <div className="report-info">
                  <h3>
                    <FileText size={20} />
                    {analysis.filename || 'Gait Analysis Report'}
                  </h3>
                  <div className="report-meta">
                    <span className="report-date">
                      <Calendar size={14} />
                      {formatDate(analysis.updated_at || analysis.created_at)}
                    </span>
                    <span className="report-id">ID: {analysis.id.substring(0, 8)}...</span>
                  </div>
                </div>
                <div className="report-status">
                  <span className="status-badge completed">Completed</span>
                </div>
              </div>

              {analysis.metrics && (
                <div className="report-summary">
                  {analysis.metrics.walking_speed && (
                    <div className="summary-metric">
                      <span className="metric-label">Walking Speed</span>
                      <span className="metric-value">
                        {(analysis.metrics.walking_speed / 1000).toFixed(2)} m/s
                      </span>
                    </div>
                  )}
                  {analysis.metrics.cadence && (
                    <div className="summary-metric">
                      <span className="metric-label">Cadence</span>
                      <span className="metric-value">
                        {analysis.metrics.cadence.toFixed(0)} steps/min
                      </span>
                    </div>
                  )}
                  {analysis.metrics.fall_risk_assessment?.risk_level && (
                    <div className="summary-metric">
                      <span className="metric-label">Fall Risk</span>
                      <span 
                        className="metric-value risk-level"
                        style={{ color: getRiskLevelColor(analysis.metrics.fall_risk_assessment.risk_level) }}
                      >
                        {analysis.metrics.fall_risk_assessment.risk_level}
                      </span>
                    </div>
                  )}
                  {analysis.metrics.functional_mobility?.mobility_level && (
                    <div className="summary-metric">
                      <span className="metric-label">Mobility</span>
                      <span 
                        className="metric-value mobility-level"
                        style={{ color: getMobilityLevelColor(analysis.metrics.functional_mobility.mobility_level) }}
                      >
                        {analysis.metrics.functional_mobility.mobility_level}
                      </span>
                    </div>
                  )}
                </div>
              )}

              <div className="report-actions">
                <button
                  onClick={() => navigate(`/report/${analysis.id}`)}
                  className="btn btn-primary"
                >
                  View Report
                </button>
                <button
                  onClick={() => handleDelete(analysis.id, analysis.filename)}
                  className="btn btn-danger"
                  disabled={deletingId === analysis.id}
                  style={{ 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '0.5rem',
                    backgroundColor: '#e74c3c',
                    color: 'white'
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
        <button onClick={() => navigate('/')} className="btn btn-secondary">
          Upload New Video
        </button>
      </div>
    </div>
  )
}
