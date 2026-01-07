import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import './Dashboard.css'

const getApiUrl = () => {
  // If running on same domain as backend (integrated deployment), use relative URLs
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname
    // Integrated app - frontend and backend on same domain
    if (hostname.includes('azurewebsites.net') || hostname.includes('localhost')) {
      return '' // Use relative URLs - same origin
    }
    // Separate frontend deployment (if using Static Web Apps)
    if (hostname.includes('azurestaticapps.net')) {
      return 'https://gaitanalysisapp.azurewebsites.net'
    }
  }
  // Development fallback
  return (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000'
}

const API_URL = getApiUrl()

interface AnalysisResult {
  id: string
  status: string
  metrics?: {
    cadence?: number
    step_length?: number
    walking_speed?: number
    stride_length?: number
    double_support_time?: number
    swing_time?: number
    stance_time?: number
  }
  reports?: {
    medical?: any
  }
}

export default function MedicalDashboard() {
  const [searchParams] = useSearchParams()
  const analysisId = searchParams.get('analysisId')
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (analysisId) {
      fetchAnalysis(analysisId)
    } else {
      setError('No analysis ID provided')
      setLoading(false)
    }
  }, [analysisId])

  const fetchAnalysis = async (id: string) => {
    try {
      setLoading(true)
      setError(null)
      
      const url = `${API_URL}/api/v1/analysis/${id}`
      console.log('Fetching analysis from:', url)
      
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
      })
      
      console.log('Response status:', response.status)
      
      if (!response.ok) {
        const errorText = await response.text()
        console.error('API Error:', errorText)
        throw new Error(`Failed to fetch analysis (${response.status}): ${errorText || response.statusText}`)
      }
      
      const data = await response.json()
      console.log('Analysis data:', data)
      setAnalysis(data)
    } catch (err: any) {
      console.error('Fetch error:', err)
      setError(err.message || 'Failed to load analysis. Please check the analysis ID and try again.')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="dashboard">
        <h2>Medical Dashboard</h2>
        <p>Loading analysis results...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="dashboard">
        <h2>Medical Dashboard</h2>
        <div className="error-message">
          <p>Error: {error}</p>
          {analysisId && (
            <button onClick={() => fetchAnalysis(analysisId)} className="btn btn-primary">
              Retry
            </button>
          )}
        </div>
      </div>
    )
  }

  if (!analysis) {
    return (
      <div className="dashboard">
        <h2>Medical Dashboard</h2>
        <p>No analysis data available. Please upload a video first.</p>
      </div>
    )
  }

  const metrics = analysis.metrics || {}
  const status = analysis.status || 'unknown'

  return (
    <div className="dashboard">
      <h2>Medical Dashboard</h2>
      
      <div className="dashboard-section">
        <h3>Analysis Information</h3>
        <div className="info-grid">
          <div className="info-item">
            <strong>Analysis ID:</strong> {analysis.id}
          </div>
          <div className="info-item">
            <strong>Status:</strong> <span className={`status-badge status-${status}`}>{status}</span>
          </div>
        </div>
      </div>

      {status === 'completed' && metrics && Object.keys(metrics).length > 0 && (
        <div className="dashboard-section">
          <h3>Gait Metrics</h3>
          <div className="metrics-grid">
            {metrics.cadence && (
              <div className="metric-card">
                <div className="metric-label">Cadence</div>
                <div className="metric-value">{metrics.cadence.toFixed(2)}</div>
                <div className="metric-unit">steps/min</div>
              </div>
            )}
            {metrics.step_length && (
              <div className="metric-card">
                <div className="metric-label">Step Length</div>
                <div className="metric-value">{(metrics.step_length / 1000).toFixed(2)}</div>
                <div className="metric-unit">m</div>
              </div>
            )}
            {metrics.walking_speed && (
              <div className="metric-card">
                <div className="metric-label">Walking Speed</div>
                <div className="metric-value">{(metrics.walking_speed / 1000).toFixed(2)}</div>
                <div className="metric-unit">m/s</div>
              </div>
            )}
            {metrics.stride_length && (
              <div className="metric-card">
                <div className="metric-label">Stride Length</div>
                <div className="metric-value">{(metrics.stride_length / 1000).toFixed(2)}</div>
                <div className="metric-unit">m</div>
              </div>
            )}
            {metrics.double_support_time && (
              <div className="metric-card">
                <div className="metric-label">Double Support Time</div>
                <div className="metric-value">{metrics.double_support_time.toFixed(3)}</div>
                <div className="metric-unit">s</div>
              </div>
            )}
            {metrics.swing_time && (
              <div className="metric-card">
                <div className="metric-label">Swing Time</div>
                <div className="metric-value">{metrics.swing_time.toFixed(3)}</div>
                <div className="metric-unit">s</div>
              </div>
            )}
            {metrics.stance_time && (
              <div className="metric-card">
                <div className="metric-label">Stance Time</div>
                <div className="metric-value">{metrics.stance_time.toFixed(3)}</div>
                <div className="metric-unit">s</div>
              </div>
            )}
          </div>
        </div>
      )}

      {status === 'processing' && (
        <div className="dashboard-section">
          <div className="processing-message">
            <p>Analysis is currently processing. Please check back in a few moments.</p>
            <button onClick={() => analysisId && fetchAnalysis(analysisId)} className="btn btn-primary">
              Refresh Status
            </button>
          </div>
        </div>
      )}

      {!analysisId && (
        <div className="dashboard-section">
          <p>To view analysis results, please upload a video first.</p>
        </div>
      )}
    </div>
  )
}
