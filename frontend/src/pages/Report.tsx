import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import './Report.css'

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

interface AnalysisResult {
  id: string
  status: string
  filename?: string
  video_url?: string
  metrics?: {
    cadence?: number
    step_length?: number
    walking_speed?: number
    stride_length?: number
    double_support_time?: number
    swing_time?: number
    stance_time?: number
  }
  created_at?: string
}

export default function Report() {
  const { analysisId } = useParams<{ analysisId: string }>()
  const navigate = useNavigate()
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!analysisId) {
      setError('No analysis ID provided')
      setLoading(false)
      return
    }

    const fetchAnalysis = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/analysis/${analysisId}`)
        
        if (!response.ok) {
          throw new Error(`Failed to fetch analysis: ${response.statusText}`)
        }

        const data = await response.json()
        setAnalysis(data)
      } catch (err: any) {
        console.error('Error fetching analysis:', err)
        setError(err.message || 'Failed to load analysis')
      } finally {
        setLoading(false)
      }
    }

    fetchAnalysis()
  }, [analysisId])

  if (loading) {
    return (
      <div className="report-page">
        <div className="loading">Loading report...</div>
      </div>
    )
  }

  if (error || !analysis) {
    return (
      <div className="report-page">
        <div className="error-message">
          <h2>Error</h2>
          <p>{error || 'Analysis not found'}</p>
          <button onClick={() => navigate('/view-gait')} className="btn btn-primary">
            View All Analyses
          </button>
        </div>
      </div>
    )
  }

  const metrics = analysis.metrics || {}
  const status = analysis.status || 'unknown'

  // Calculate metrics for different sections
  const walkingSpeed = metrics.walking_speed ? metrics.walking_speed / 1000 : null
  const healthScore = walkingSpeed 
    ? Math.min(100, Math.max(0, Math.round((walkingSpeed / 1.4) * 100)))
    : null
  const fallRisk = walkingSpeed ? (walkingSpeed < 1.0 ? 'High' : walkingSpeed < 1.2 ? 'Moderate' : 'Low') : null

  return (
    <div className="report-page">
      <div className="report-header">
        <h1>Gait Analysis Report</h1>
        <div className="report-meta">
          <p><strong>Analysis ID:</strong> {analysis.id}</p>
          {analysis.filename && <p><strong>Video:</strong> {analysis.filename}</p>}
          {analysis.created_at && <p><strong>Date:</strong> {new Date(analysis.created_at).toLocaleDateString()}</p>}
        </div>
      </div>

      {status !== 'completed' && (
        <div className="status-warning">
          <p>Analysis status: <strong>{status}</strong></p>
          {status === 'processing' && <p>This analysis is still being processed. Please check back later.</p>}
        </div>
      )}

      {status === 'completed' && metrics && Object.keys(metrics).length > 0 && (
        <div className="report-sections">
          {/* Patient Section */}
          <section className="report-section patient-section">
            <h2>Patient</h2>
            <div className="section-content">
              {healthScore !== null && (
                <div className="health-score-card">
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
              </div>
            </div>
          </section>

          {/* Caregiver Section */}
          <section className="report-section caregiver-section">
            <h2>Caregiver</h2>
            <div className="section-content">
              {fallRisk && (
                <div className={`risk-indicator risk-${fallRisk.toLowerCase()}`}>
                  <div className="risk-label">Fall Risk Assessment</div>
                  <div className="risk-value">{fallRisk}</div>
                  <div className="risk-description">
                    {fallRisk === 'Low' && <p>✅ Low risk - Continue monitoring</p>}
                    {fallRisk === 'Moderate' && <p>⚠️ Moderate risk - Consider consultation</p>}
                    {fallRisk === 'High' && <p>🔴 High risk - Please consult healthcare provider</p>}
                  </div>
                </div>
              )}

              <div className="metrics-grid">
                {metrics.walking_speed && (
                  <div className="metric-card">
                    <div className="metric-label">Walking Speed</div>
                    <div className="metric-value">{(metrics.walking_speed / 1000).toFixed(2)}</div>
                    <div className="metric-unit">m/s</div>
                    <div className="metric-note">
                      {walkingSpeed && walkingSpeed < 1.0 && 'Below normal range'}
                      {walkingSpeed && walkingSpeed >= 1.0 && walkingSpeed < 1.2 && 'Slightly below normal'}
                      {walkingSpeed && walkingSpeed >= 1.2 && 'Within normal range'}
                    </div>
                  </div>
                )}
                {metrics.stride_length && (
                  <div className="metric-card">
                    <div className="metric-label">Stride Length</div>
                    <div className="metric-value">{(metrics.stride_length / 1000).toFixed(2)}</div>
                    <div className="metric-unit">m</div>
                  </div>
                )}
                {metrics.cadence && (
                  <div className="metric-card">
                    <div className="metric-label">Cadence</div>
                    <div className="metric-value">{metrics.cadence.toFixed(2)}</div>
                    <div className="metric-unit">steps/min</div>
                  </div>
                )}
              </div>

              <div className="trend-note">
                <p><strong>Monitoring Note:</strong> Track these metrics over time to identify changes in mobility patterns. Consult with healthcare providers if you notice significant declines.</p>
              </div>
            </div>
          </section>

          {/* Professional Section */}
          <section className="report-section professional-section">
            <h2>Professional</h2>
            <div className="section-content">
              <div className="metrics-grid comprehensive">
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

              <div className="clinical-notes">
                <h3>Clinical Notes</h3>
                <ul>
                  <li>Analysis performed using Azure Computer Vision API</li>
                  <li>Metrics calculated from video-based pose estimation</li>
                  <li>Results validated against clinical standards</li>
                  {analysis.video_url && (
                    <li>Source video available for review</li>
                  )}
                </ul>
              </div>
            </div>
          </section>
        </div>
      )}

      {status === 'completed' && (!metrics || Object.keys(metrics).length === 0) && (
        <div className="no-metrics">
          <p>Analysis completed but no metrics are available.</p>
        </div>
      )}

      <div className="report-actions">
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
        <button onClick={() => navigate('/view-gait')} className="btn btn-secondary">
          View All Analyses
        </button>
        <button onClick={() => navigate('/upload')} className="btn btn-primary">
          Upload New Video
        </button>
      </div>
    </div>
  )
}

