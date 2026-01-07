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
  }
}

export default function OlderAdultDashboard() {
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
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
      })
      
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Failed to fetch analysis (${response.status}): ${errorText || response.statusText}`)
      }
      
      const data = await response.json()
      setAnalysis(data)
    } catch (err: any) {
      setError(err.message || 'Failed to load analysis. Please check the analysis ID and try again.')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="dashboard">
        <h2>Your Dashboard</h2>
        <p>Loading your results...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="dashboard">
        <h2>Your Dashboard</h2>
        <div className="error-message">
          <p>Error: {error}</p>
          {analysisId && (
            <button onClick={() => fetchAnalysis(analysisId)} className="btn btn-primary">
              Try Again
            </button>
          )}
        </div>
      </div>
    )
  }

  if (!analysis) {
    return (
      <div className="dashboard">
        <h2>Your Dashboard</h2>
        <p>No results available yet. Please upload a video to get started.</p>
      </div>
    )
  }

  const metrics = analysis.metrics || {}
  const status = analysis.status || 'unknown'
  
  // Calculate gait health score (0-100, simplified)
  const walkingSpeed = metrics.walking_speed ? metrics.walking_speed / 1000 : null
  const healthScore = walkingSpeed 
    ? Math.min(100, Math.max(0, Math.round((walkingSpeed / 1.4) * 100)))
    : null

  return (
    <div className="dashboard">
      <h2>Your Gait Analysis</h2>
      
      {status === 'completed' && metrics && Object.keys(metrics).length > 0 && (
        <>
          {healthScore !== null && (
            <div className="dashboard-section">
              <h3>Your Gait Health Score</h3>
              <div className="health-score">
                <div className="score-value">{healthScore}</div>
                <div className="score-label">out of 100</div>
                <div className="score-description">
                  {healthScore >= 80 && <p>✅ Excellent! Keep up the great work!</p>}
                  {healthScore >= 60 && healthScore < 80 && <p>👍 Good! Your mobility looks healthy.</p>}
                  {healthScore < 60 && <p>💪 Focus on regular movement and activity.</p>}
                </div>
              </div>
            </div>
          )}

          <div className="dashboard-section">
            <h3>Your Movement Summary</h3>
            <div className="simple-metrics">
              {metrics.walking_speed && (
                <div className="simple-metric">
                  <div className="simple-label">Walking Speed</div>
                  <div className="simple-value">{(metrics.walking_speed / 1000).toFixed(2)} m/s</div>
                </div>
              )}
              {metrics.cadence && (
                <div className="simple-metric">
                  <div className="simple-label">Steps per Minute</div>
                  <div className="simple-value">{metrics.cadence.toFixed(0)}</div>
                </div>
              )}
              {metrics.step_length && (
                <div className="simple-metric">
                  <div className="simple-label">Step Length</div>
                  <div className="simple-value">{(metrics.step_length / 1000).toFixed(2)} m</div>
                </div>
              )}
            </div>
          </div>

          <div className="dashboard-section">
            <div className="encouragement-box">
              <p>📊 Your movement analysis helps track your mobility over time. Regular check-ins can help maintain healthy movement patterns.</p>
            </div>
          </div>
        </>
      )}

      {status === 'processing' && (
        <div className="dashboard-section">
          <div className="processing-message">
            <p>Your analysis is being processed. This usually takes a few minutes.</p>
            <button onClick={() => analysisId && fetchAnalysis(analysisId)} className="btn btn-primary">
              Check Again
            </button>
          </div>
        </div>
      )}

      {!analysisId && (
        <div className="dashboard-section">
          <p>Upload a video to see your gait analysis results here.</p>
        </div>
      )}
    </div>
  )
}
