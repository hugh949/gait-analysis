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
    step_time?: number
    // Geriatric-specific parameters
    step_width_mean?: number
    step_width_cv?: number
    walk_ratio?: number
    stride_speed_cv?: number
    step_length_cv?: number
    step_time_cv?: number
    step_time_symmetry?: number
    step_length_symmetry?: number
    // Professional assessments
    fall_risk_assessment?: {
      risk_score?: number
      risk_level?: string
      risk_category?: string
      risk_factors?: string[]
      risk_factor_count?: number
      walking_speed_mps?: number
      normalized_stride_length?: number
    }
    functional_mobility?: {
      mobility_score?: number
      mobility_level?: string
      mobility_category?: string
      score_percentage?: number
    }
    directional_analysis?: {
      primary_direction?: string
      direction_confidence?: number
    }
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

  // Use professional assessments from backend if available
  const fallRiskAssessment = metrics.fall_risk_assessment || {}
  const functionalMobility = metrics.functional_mobility || {}
  
  // Calculate metrics for different sections
  const walkingSpeed = metrics.walking_speed ? metrics.walking_speed / 1000 : null
  const healthScore = functionalMobility.mobility_score || (walkingSpeed 
    ? Math.min(100, Math.max(0, Math.round((walkingSpeed / 1.4) * 100)))
    : null)

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
              {fallRiskAssessment.risk_level && (
                <div className={`risk-indicator risk-${fallRiskAssessment.risk_level.toLowerCase()}`}>
                  <div className="risk-label">Professional Fall Risk Assessment</div>
                  <div className="risk-value">{fallRiskAssessment.risk_level}</div>
                  <div className="risk-score">Risk Score: {fallRiskAssessment.risk_score?.toFixed(1) || 'N/A'}</div>
                  <div className="risk-description">
                    <p>{fallRiskAssessment.risk_category || 'Assessment in progress'}</p>
                    {fallRiskAssessment.risk_factors && fallRiskAssessment.risk_factors.length > 0 && (
                      <div className="risk-factors">
                        <p><strong>Key Risk Factors:</strong></p>
                        <ul>
                          {fallRiskAssessment.risk_factors.slice(0, 5).map((factor, idx) => (
                            <li key={idx}>{factor}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {functionalMobility.mobility_level && (
                <div className="mobility-indicator">
                  <div className="mobility-label">Functional Mobility Assessment</div>
                  <div className="mobility-value">{functionalMobility.mobility_level}</div>
                  <div className="mobility-score">
                    Score: {functionalMobility.mobility_score?.toFixed(1) || 'N/A'} / 100
                    ({functionalMobility.score_percentage?.toFixed(1) || '0'}%)
                  </div>
                  <div className="mobility-description">
                    <p>{functionalMobility.mobility_category || 'Assessment in progress'}</p>
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
            <h2>Professional Gait Lab Parameters</h2>
            <div className="section-content">
              <h3>Spatiotemporal Parameters</h3>
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
                {metrics.step_time && (
                  <div className="metric-card">
                    <div className="metric-label">Step Time</div>
                    <div className="metric-value">{metrics.step_time.toFixed(3)}</div>
                    <div className="metric-unit">s</div>
                  </div>
                )}
              </div>

              <h3>Geriatric Fall Risk Parameters</h3>
              <div className="metrics-grid comprehensive">
                {metrics.step_width_mean !== undefined && (
                  <div className="metric-card">
                    <div className="metric-label">Step Width (Mean)</div>
                    <div className="metric-value">{(metrics.step_width_mean / 1000).toFixed(3)}</div>
                    <div className="metric-unit">m</div>
                    <div className="metric-note">Base of support</div>
                  </div>
                )}
                {metrics.step_width_cv !== undefined && (
                  <div className="metric-card">
                    <div className="metric-label">Step Width Variability</div>
                    <div className="metric-value">{metrics.step_width_cv.toFixed(2)}</div>
                    <div className="metric-unit">% CV</div>
                    <div className="metric-note">
                      {metrics.step_width_cv > 15 ? '⚠️ High variability' : 
                       metrics.step_width_cv > 10 ? '⚠️ Moderate variability' : 
                       '✅ Normal variability'}
                    </div>
                  </div>
                )}
                {metrics.walk_ratio !== undefined && (
                  <div className="metric-card">
                    <div className="metric-label">Walk Ratio</div>
                    <div className="metric-value">{metrics.walk_ratio.toFixed(4)}</div>
                    <div className="metric-unit">mm/(steps/min)</div>
                    <div className="metric-note">Gait efficiency indicator</div>
                  </div>
                )}
                {metrics.stride_speed_cv !== undefined && (
                  <div className="metric-card">
                    <div className="metric-label">Stride Speed Variability</div>
                    <div className="metric-value">{metrics.stride_speed_cv.toFixed(2)}</div>
                    <div className="metric-unit">% CV</div>
                    <div className="metric-note">Strongest fall predictor</div>
                  </div>
                )}
                {metrics.step_length_cv !== undefined && (
                  <div className="metric-card">
                    <div className="metric-label">Step Length Variability</div>
                    <div className="metric-value">{metrics.step_length_cv.toFixed(2)}</div>
                    <div className="metric-unit">% CV</div>
                  </div>
                )}
                {metrics.step_time_cv !== undefined && (
                  <div className="metric-card">
                    <div className="metric-label">Step Time Variability</div>
                    <div className="metric-value">{metrics.step_time_cv.toFixed(2)}</div>
                    <div className="metric-unit">% CV</div>
                  </div>
                )}
              </div>

              <h3>Gait Symmetry</h3>
              <div className="metrics-grid comprehensive">
                {metrics.step_time_symmetry !== undefined && (
                  <div className="metric-card">
                    <div className="metric-label">Step Time Symmetry</div>
                    <div className="metric-value">{(metrics.step_time_symmetry * 100).toFixed(1)}</div>
                    <div className="metric-unit">%</div>
                    <div className="metric-note">
                      {metrics.step_time_symmetry >= 0.85 ? '✅ Good symmetry' : '⚠️ Asymmetry detected'}
                    </div>
                  </div>
                )}
                {metrics.step_length_symmetry !== undefined && (
                  <div className="metric-card">
                    <div className="metric-label">Step Length Symmetry</div>
                    <div className="metric-value">{(metrics.step_length_symmetry * 100).toFixed(1)}</div>
                    <div className="metric-unit">%</div>
                  </div>
                )}
              </div>

              {metrics.directional_analysis && (
                <div className="directional-info">
                  <h3>Multi-Directional Analysis</h3>
                  <p><strong>Primary Direction:</strong> {metrics.directional_analysis.primary_direction || 'Unknown'}</p>
                  <p><strong>Confidence:</strong> {metrics.directional_analysis.direction_confidence 
                    ? `${(metrics.directional_analysis.direction_confidence * 100).toFixed(1)}%`
                    : 'N/A'}</p>
                </div>
              )}

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

