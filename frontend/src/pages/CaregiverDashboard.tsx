import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import './Dashboard.css'

const getApiUrl = () => {
  if (typeof window !== 'undefined' && window.location.hostname.includes('azurestaticapps.net')) {
    return 'https://gait-analysis-api-simple.azurewebsites.net'
  }
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

export default function CaregiverDashboard() {
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
      const response = await fetch(`${API_URL}/api/v1/analysis/${id}`)
      
      if (!response.ok) {
        throw new Error(`Failed to fetch analysis: ${response.statusText}`)
      }
      
      const data = await response.json()
      setAnalysis(data)
    } catch (err: any) {
      setError(err.message || 'Failed to load analysis')
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="dashboard">
        <h2>Caregiver Dashboard</h2>
        <p>Loading analysis results...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="dashboard">
        <h2>Caregiver Dashboard</h2>
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
        <h2>Caregiver Dashboard</h2>
        <p>No analysis data available. Please upload a video first.</p>
      </div>
    )
  }

  const metrics = analysis.metrics || {}
  const status = analysis.status || 'unknown'
  
  // Calculate fall risk indicator (simplified)
  const walkingSpeed = metrics.walking_speed ? metrics.walking_speed / 1000 : null
  const fallRisk = walkingSpeed ? (walkingSpeed < 1.0 ? 'High' : walkingSpeed < 1.2 ? 'Moderate' : 'Low') : null

  return (
    <div className="dashboard">
      <h2>Caregiver Dashboard</h2>
      
      <div className="dashboard-section">
        <h3>Overview</h3>
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
        <>
          {fallRisk && (
            <div className="dashboard-section">
              <h3>Fall Risk Assessment</h3>
              <div className={`risk-indicator risk-${fallRisk.toLowerCase()}`}>
                <div className="risk-label">Fall Risk Level</div>
                <div className="risk-value">{fallRisk}</div>
                {fallRisk === 'High' && (
                  <div className="risk-note">
                    <p>⚠️ Consider consulting with a healthcare professional for further assessment.</p>
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="dashboard-section">
            <h3>Key Mobility Metrics</h3>
            <div className="metrics-grid">
              {metrics.walking_speed && (
                <div className="metric-card">
                  <div className="metric-label">Walking Speed</div>
                  <div className="metric-value">{(metrics.walking_speed / 1000).toFixed(2)}</div>
                  <div className="metric-unit">m/s</div>
                </div>
              )}
              {metrics.cadence && (
                <div className="metric-card">
                  <div className="metric-label">Steps per Minute</div>
                  <div className="metric-value">{metrics.cadence.toFixed(0)}</div>
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
            </div>
          </div>

          <div className="dashboard-section">
            <div className="note-box">
              <p><strong>Note:</strong> These metrics are for informational purposes. Always consult with healthcare professionals for clinical decisions.</p>
            </div>
          </div>
        </>
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
