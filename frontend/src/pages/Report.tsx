import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { AlertCircle, Info, TrendingUp, Activity, Shield } from 'lucide-react'
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
  current_step?: string
  step_progress?: number
  step_message?: string
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
  // Video quality validation fields
  video_quality_score?: number
  video_quality_valid?: boolean
  video_quality_issues?: string[]
  video_quality_recommendations?: string[]
  pose_detection_rate?: number
}

// Parameter definitions for professional reports
const PARAMETER_DEFINITIONS = {
  cadence: {
    name: "Cadence",
    description: "Number of steps taken per minute. Normal range: 100-120 steps/min for healthy adults.",
    clinicalSignificance: "Lower cadence may indicate mobility issues or cautious gait patterns."
  },
  step_length: {
    name: "Step Length",
    description: "Distance from heel contact of one foot to heel contact of the opposite foot. Measured in meters.",
    clinicalSignificance: "Shorter step length may indicate reduced mobility, muscle weakness, or balance concerns."
  },
  stride_length: {
    name: "Stride Length",
    description: "Distance from heel contact of one foot to the next heel contact of the same foot (two steps).",
    clinicalSignificance: "Reduced stride length is associated with increased fall risk in older adults."
  },
  walking_speed: {
    name: "Walking Speed",
    description: "Average forward velocity during walking. Normal: >1.2 m/s for healthy adults.",
    clinicalSignificance: "Walking speed <1.0 m/s is a strong predictor of fall risk and functional decline."
  },
  step_time: {
    name: "Step Time",
    description: "Time taken to complete one step (heel contact to opposite heel contact).",
    clinicalSignificance: "Increased step time may indicate balance issues or cautious gait."
  },
  stance_time: {
    name: "Stance Time",
    description: "Time the foot is in contact with the ground during a step cycle (typically 60% of step time).",
    clinicalSignificance: "Increased stance time may indicate balance concerns or reduced confidence."
  },
  swing_time: {
    name: "Swing Time",
    description: "Time the foot is off the ground during a step cycle (typically 40% of step time).",
    clinicalSignificance: "Reduced swing time may indicate muscle weakness or balance issues."
  },
  double_support_time: {
    name: "Double Support Time",
    description: "Time when both feet are in contact with the ground (typically 10-12% of step time).",
    clinicalSignificance: "Increased double support time (>15%) is associated with higher fall risk."
  },
  step_width_mean: {
    name: "Step Width (Mean)",
    description: "Average lateral distance between feet during walking. Normal: 8-10 cm.",
    clinicalSignificance: "Wider step width may indicate balance compensation or instability."
  },
  step_width_cv: {
    name: "Step Width Variability",
    description: "Coefficient of variation in step width (consistency measure). Lower is better.",
    clinicalSignificance: "High variability (>15%) indicates unstable gait and increased fall risk."
  },
  walk_ratio: {
    name: "Walk Ratio",
    description: "Step length divided by cadence. Normal: 0.5-0.6 mm/(steps/min).",
    clinicalSignificance: "Lower walk ratio indicates less efficient gait pattern."
  },
  stride_speed_cv: {
    name: "Stride Speed Variability",
    description: "Coefficient of variation in stride-to-stride speed. Strongest predictor of falls.",
    clinicalSignificance: "CV >5% indicates high fall risk. CV >10% indicates very high risk."
  },
  step_length_cv: {
    name: "Step Length Variability",
    description: "Coefficient of variation in step length (consistency measure).",
    clinicalSignificance: "High variability indicates unstable gait pattern."
  },
  step_time_cv: {
    name: "Step Time Variability",
    description: "Coefficient of variation in step time (rhythm consistency).",
    clinicalSignificance: "High variability indicates irregular gait rhythm."
  },
  step_time_symmetry: {
    name: "Step Time Symmetry",
    description: "Ratio of left to right step times. 1.0 = perfect symmetry. Normal: 0.85-1.15.",
    clinicalSignificance: "Asymmetry <0.85 or >1.15 may indicate unilateral weakness or injury."
  },
  step_length_symmetry: {
    name: "Step Length Symmetry",
    description: "Ratio of left to right step lengths. 1.0 = perfect symmetry.",
    clinicalSignificance: "Asymmetry may indicate compensation patterns or unilateral issues."
  }
}

export default function Report() {
  const { analysisId } = useParams<{ analysisId: string }>()
  const navigate = useNavigate()
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedParams, setExpandedParams] = useState<Set<string>>(new Set())

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

  const toggleParamExplanation = (paramKey: string) => {
    const newExpanded = new Set(expandedParams)
    if (newExpanded.has(paramKey)) {
      newExpanded.delete(paramKey)
    } else {
      newExpanded.add(paramKey)
    }
    setExpandedParams(newExpanded)
  }

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
          <button onClick={() => navigate('/view-reports')} className="btn btn-primary">
            View All Reports
          </button>
        </div>
      </div>
    )
  }

  // Check if this was force-completed
  const isForceCompleted = analysis.step_message?.includes('force complete') || false

  // If analysis is still processing, redirect to upload page
  const status = analysis.status || 'unknown'
  
  if (status === 'processing') {
    return (
      <div className="report-page">
        <div className="processing-redirect">
          <h2>Analysis Still Processing</h2>
          <p>This analysis is still being processed. Please check the progress on the Upload Video page.</p>
          <div className="redirect-actions">
            <button onClick={() => navigate('/upload')} className="btn btn-primary">
              Go to Upload Video
            </button>
            <button onClick={() => navigate('/view-reports')} className="btn btn-secondary">
              View Other Reports
            </button>
          </div>
        </div>
      </div>
    )
  }

  const metrics = analysis.metrics || {}

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
      {/* Professional Report Header */}
      <div className="report-header-professional">
        <div className="report-header-content">
          <h1>Gait Analysis Report</h1>
          <p className="report-subtitle">Clinical-Grade Gait Assessment</p>
        </div>
        <div className="report-meta-professional">
          <div className="meta-item">
            <span className="meta-label">Analysis ID:</span>
            <span className="meta-value">{analysis.id}</span>
          </div>
          {analysis.filename && (
            <div className="meta-item">
              <span className="meta-label">Video:</span>
              <span className="meta-value">{analysis.filename}</span>
            </div>
          )}
          {analysis.created_at && (
            <div className="meta-item">
              <span className="meta-label">Date:</span>
              <span className="meta-value">{new Date(analysis.created_at).toLocaleDateString('en-US', { 
                year: 'numeric', 
                month: 'long', 
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
              })}</span>
            </div>
          )}
          {isForceCompleted && (
            <div className="meta-item warning">
              <span className="meta-label">Note:</span>
              <span className="meta-value">Analysis completed via recovery process</span>
            </div>
          )}
        </div>
      </div>

      {status === 'failed' && (
        <div className="status-error">
          <AlertCircle size={24} />
          <p>Analysis failed. Please try uploading again.</p>
          <button onClick={() => navigate('/upload')} className="btn btn-primary">
            Upload New Video
          </button>
        </div>
      )}

      {status === 'completed' && metrics && Object.keys(metrics).length > 0 && (
        <div className="report-sections-professional">
          {/* Executive Summary Section */}
          <section className="report-section executive-summary">
            <div className="section-header">
              <Activity className="section-icon" size={24} />
              <h2>Executive Summary</h2>
            </div>
            <div className="summary-grid">
              {healthScore !== null && (
                <div className="summary-card primary">
                  <div className="summary-card-header">
                    <TrendingUp size={20} />
                    <span>Gait Health Score</span>
                  </div>
                  <div className="summary-card-value">{healthScore}</div>
                  <div className="summary-card-label">out of 100</div>
                  <div className="summary-card-description">
                    {healthScore >= 80 && <p>✅ Excellent mobility and gait function</p>}
                    {healthScore >= 60 && healthScore < 80 && <p>👍 Good mobility with room for improvement</p>}
                    {healthScore < 60 && <p>💪 Focus on regular movement and activity</p>}
                  </div>
                </div>
              )}

              {fallRiskAssessment.risk_level && (
                <div className={`summary-card risk-${fallRiskAssessment.risk_level.toLowerCase()}`}>
                  <div className="summary-card-header">
                    <Shield size={20} />
                    <span>Fall Risk Assessment</span>
                  </div>
                  <div className="summary-card-value">{fallRiskAssessment.risk_level}</div>
                  <div className="summary-card-label">Risk Score: {fallRiskAssessment.risk_score?.toFixed(1) || 'N/A'}</div>
                  <div className="summary-card-description">
                    <p>{fallRiskAssessment.risk_category || 'Assessment complete'}</p>
                  </div>
                </div>
              )}

              {walkingSpeed !== null && (
                <div className="summary-card">
                  <div className="summary-card-header">
                    <Activity size={20} />
                    <span>Walking Speed</span>
                  </div>
                  <div className="summary-card-value">{walkingSpeed.toFixed(2)}</div>
                  <div className="summary-card-label">m/s</div>
                  <div className="summary-card-description">
                    {walkingSpeed < 1.0 && <p className="warning">⚠️ Below normal range (&lt;1.0 m/s)</p>}
                    {walkingSpeed >= 1.0 && walkingSpeed < 1.2 && <p className="caution">⚠️ Slightly below normal (1.0-1.2 m/s)</p>}
                    {walkingSpeed >= 1.2 && <p className="good">✅ Within normal range (≥1.2 m/s)</p>}
                  </div>
                </div>
              )}

              {metrics.cadence && (
                <div className="summary-card">
                  <div className="summary-card-header">
                    <Activity size={20} />
                    <span>Cadence</span>
                  </div>
                  <div className="summary-card-value">{metrics.cadence.toFixed(1)}</div>
                  <div className="summary-card-label">steps/min</div>
                  <div className="summary-card-description">
                    <p>Normal range: 100-120 steps/min</p>
                  </div>
                </div>
              )}
            </div>
          </section>

          {/* Primary Gait Parameters */}
          <section className="report-section primary-parameters">
            <div className="section-header">
              <Activity className="section-icon" size={24} />
              <h2>Primary Gait Parameters</h2>
            </div>
            <div className="parameters-grid">
              {metrics.walking_speed && (
                <div className="parameter-card">
                  <div className="parameter-header">
                    <span className="parameter-name">Walking Speed</span>
                    <button 
                      className="info-button"
                      onClick={() => toggleParamExplanation('walking_speed')}
                      title="Learn more about this parameter"
                    >
                      <Info size={16} />
                    </button>
                  </div>
                  <div className="parameter-value">{(metrics.walking_speed / 1000).toFixed(2)}</div>
                  <div className="parameter-unit">m/s</div>
                  {expandedParams.has('walking_speed') && (
                    <div className="parameter-explanation">
                      <p><strong>{PARAMETER_DEFINITIONS.walking_speed.description}</strong></p>
                      <p className="clinical-note">{PARAMETER_DEFINITIONS.walking_speed.clinicalSignificance}</p>
                    </div>
                  )}
                </div>
              )}

              {metrics.cadence && (
                <div className="parameter-card">
                  <div className="parameter-header">
                    <span className="parameter-name">Cadence</span>
                    <button 
                      className="info-button"
                      onClick={() => toggleParamExplanation('cadence')}
                      title="Learn more about this parameter"
                    >
                      <Info size={16} />
                    </button>
                  </div>
                  <div className="parameter-value">{metrics.cadence.toFixed(1)}</div>
                  <div className="parameter-unit">steps/min</div>
                  {expandedParams.has('cadence') && (
                    <div className="parameter-explanation">
                      <p><strong>{PARAMETER_DEFINITIONS.cadence.description}</strong></p>
                      <p className="clinical-note">{PARAMETER_DEFINITIONS.cadence.clinicalSignificance}</p>
                    </div>
                  )}
                </div>
              )}

              {metrics.step_length && (
                <div className="parameter-card">
                  <div className="parameter-header">
                    <span className="parameter-name">Step Length</span>
                    <button 
                      className="info-button"
                      onClick={() => toggleParamExplanation('step_length')}
                      title="Learn more about this parameter"
                    >
                      <Info size={16} />
                    </button>
                  </div>
                  <div className="parameter-value">{(metrics.step_length / 1000).toFixed(2)}</div>
                  <div className="parameter-unit">m</div>
                  {expandedParams.has('step_length') && (
                    <div className="parameter-explanation">
                      <p><strong>{PARAMETER_DEFINITIONS.step_length.description}</strong></p>
                      <p className="clinical-note">{PARAMETER_DEFINITIONS.step_length.clinicalSignificance}</p>
                    </div>
                  )}
                </div>
              )}

              {metrics.stride_length && (
                <div className="parameter-card">
                  <div className="parameter-header">
                    <span className="parameter-name">Stride Length</span>
                    <button 
                      className="info-button"
                      onClick={() => toggleParamExplanation('stride_length')}
                      title="Learn more about this parameter"
                    >
                      <Info size={16} />
                    </button>
                  </div>
                  <div className="parameter-value">{(metrics.stride_length / 1000).toFixed(2)}</div>
                  <div className="parameter-unit">m</div>
                  {expandedParams.has('stride_length') && (
                    <div className="parameter-explanation">
                      <p><strong>{PARAMETER_DEFINITIONS.stride_length.description}</strong></p>
                      <p className="clinical-note">{PARAMETER_DEFINITIONS.stride_length.clinicalSignificance}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>

          {/* Temporal Parameters */}
          <section className="report-section temporal-parameters">
            <div className="section-header">
              <Activity className="section-icon" size={24} />
              <h2>Temporal Parameters</h2>
            </div>
            <div className="parameters-grid">
              {metrics.step_time && (
                <div className="parameter-card">
                  <div className="parameter-header">
                    <span className="parameter-name">Step Time</span>
                    <button 
                      className="info-button"
                      onClick={() => toggleParamExplanation('step_time')}
                      title="Learn more about this parameter"
                    >
                      <Info size={16} />
                    </button>
                  </div>
                  <div className="parameter-value">{metrics.step_time.toFixed(3)}</div>
                  <div className="parameter-unit">s</div>
                  {expandedParams.has('step_time') && (
                    <div className="parameter-explanation">
                      <p><strong>{PARAMETER_DEFINITIONS.step_time.description}</strong></p>
                      <p className="clinical-note">{PARAMETER_DEFINITIONS.step_time.clinicalSignificance}</p>
                    </div>
                  )}
                </div>
              )}

              {metrics.stance_time && (
                <div className="parameter-card">
                  <div className="parameter-header">
                    <span className="parameter-name">Stance Time</span>
                    <button 
                      className="info-button"
                      onClick={() => toggleParamExplanation('stance_time')}
                      title="Learn more about this parameter"
                    >
                      <Info size={16} />
                    </button>
                  </div>
                  <div className="parameter-value">{metrics.stance_time.toFixed(3)}</div>
                  <div className="parameter-unit">s</div>
                  {expandedParams.has('stance_time') && (
                    <div className="parameter-explanation">
                      <p><strong>{PARAMETER_DEFINITIONS.stance_time.description}</strong></p>
                      <p className="clinical-note">{PARAMETER_DEFINITIONS.stance_time.clinicalSignificance}</p>
                    </div>
                  )}
                </div>
              )}

              {metrics.swing_time && (
                <div className="parameter-card">
                  <div className="parameter-header">
                    <span className="parameter-name">Swing Time</span>
                    <button 
                      className="info-button"
                      onClick={() => toggleParamExplanation('swing_time')}
                      title="Learn more about this parameter"
                    >
                      <Info size={16} />
                    </button>
                  </div>
                  <div className="parameter-value">{metrics.swing_time.toFixed(3)}</div>
                  <div className="parameter-unit">s</div>
                  {expandedParams.has('swing_time') && (
                    <div className="parameter-explanation">
                      <p><strong>{PARAMETER_DEFINITIONS.swing_time.description}</strong></p>
                      <p className="clinical-note">{PARAMETER_DEFINITIONS.swing_time.clinicalSignificance}</p>
                    </div>
                  )}
                </div>
              )}

              {metrics.double_support_time && (
                <div className="parameter-card">
                  <div className="parameter-header">
                    <span className="parameter-name">Double Support Time</span>
                    <button 
                      className="info-button"
                      onClick={() => toggleParamExplanation('double_support_time')}
                      title="Learn more about this parameter"
                    >
                      <Info size={16} />
                    </button>
                  </div>
                  <div className="parameter-value">{metrics.double_support_time.toFixed(3)}</div>
                  <div className="parameter-unit">s</div>
                  {expandedParams.has('double_support_time') && (
                    <div className="parameter-explanation">
                      <p><strong>{PARAMETER_DEFINITIONS.double_support_time.description}</strong></p>
                      <p className="clinical-note">{PARAMETER_DEFINITIONS.double_support_time.clinicalSignificance}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </section>

          {/* Fall Risk Parameters */}
          {(metrics.step_width_mean !== undefined || metrics.step_width_cv !== undefined || 
            metrics.walk_ratio !== undefined || metrics.stride_speed_cv !== undefined) && (
            <section className="report-section fall-risk-parameters">
              <div className="section-header">
                <Shield className="section-icon" size={24} />
                <h2>Fall Risk Parameters</h2>
              </div>
              <div className="parameters-grid">
                {metrics.step_width_mean !== undefined && (
                  <div className="parameter-card">
                    <div className="parameter-header">
                      <span className="parameter-name">Step Width (Mean)</span>
                      <button 
                        className="info-button"
                        onClick={() => toggleParamExplanation('step_width_mean')}
                        title="Learn more about this parameter"
                      >
                        <Info size={16} />
                      </button>
                    </div>
                    <div className="parameter-value">{(metrics.step_width_mean / 1000).toFixed(3)}</div>
                    <div className="parameter-unit">m</div>
                    {expandedParams.has('step_width_mean') && (
                      <div className="parameter-explanation">
                        <p><strong>{PARAMETER_DEFINITIONS.step_width_mean.description}</strong></p>
                        <p className="clinical-note">{PARAMETER_DEFINITIONS.step_width_mean.clinicalSignificance}</p>
                      </div>
                    )}
                  </div>
                )}

                {metrics.step_width_cv !== undefined && (
                  <div className="parameter-card">
                    <div className="parameter-header">
                      <span className="parameter-name">Step Width Variability</span>
                      <button 
                        className="info-button"
                        onClick={() => toggleParamExplanation('step_width_cv')}
                        title="Learn more about this parameter"
                      >
                        <Info size={16} />
                      </button>
                    </div>
                    <div className="parameter-value">{metrics.step_width_cv.toFixed(2)}</div>
                    <div className="parameter-unit">% CV</div>
                    <div className={`parameter-status ${metrics.step_width_cv > 15 ? 'warning' : metrics.step_width_cv > 10 ? 'caution' : 'normal'}`}>
                      {metrics.step_width_cv > 15 ? '⚠️ High variability' : 
                       metrics.step_width_cv > 10 ? '⚠️ Moderate variability' : 
                       '✅ Normal variability'}
                    </div>
                    {expandedParams.has('step_width_cv') && (
                      <div className="parameter-explanation">
                        <p><strong>{PARAMETER_DEFINITIONS.step_width_cv.description}</strong></p>
                        <p className="clinical-note">{PARAMETER_DEFINITIONS.step_width_cv.clinicalSignificance}</p>
                      </div>
                    )}
                  </div>
                )}

                {metrics.walk_ratio !== undefined && (
                  <div className="parameter-card">
                    <div className="parameter-header">
                      <span className="parameter-name">Walk Ratio</span>
                      <button 
                        className="info-button"
                        onClick={() => toggleParamExplanation('walk_ratio')}
                        title="Learn more about this parameter"
                      >
                        <Info size={16} />
                      </button>
                    </div>
                    <div className="parameter-value">{metrics.walk_ratio.toFixed(4)}</div>
                    <div className="parameter-unit">mm/(steps/min)</div>
                    {expandedParams.has('walk_ratio') && (
                      <div className="parameter-explanation">
                        <p><strong>{PARAMETER_DEFINITIONS.walk_ratio.description}</strong></p>
                        <p className="clinical-note">{PARAMETER_DEFINITIONS.walk_ratio.clinicalSignificance}</p>
                      </div>
                    )}
                  </div>
                )}

                {metrics.stride_speed_cv !== undefined && (
                  <div className="parameter-card critical">
                    <div className="parameter-header">
                      <span className="parameter-name">Stride Speed Variability</span>
                      <button 
                        className="info-button"
                        onClick={() => toggleParamExplanation('stride_speed_cv')}
                        title="Learn more about this parameter"
                      >
                        <Info size={16} />
                      </button>
                    </div>
                    <div className="parameter-value">{metrics.stride_speed_cv.toFixed(2)}</div>
                    <div className="parameter-unit">% CV</div>
                    <div className={`parameter-status ${metrics.stride_speed_cv > 10 ? 'critical' : metrics.stride_speed_cv > 5 ? 'warning' : 'normal'}`}>
                      {metrics.stride_speed_cv > 10 ? '🔴 Very High Risk' : 
                       metrics.stride_speed_cv > 5 ? '⚠️ High Risk' : 
                       '✅ Normal'}
                    </div>
                    <div className="parameter-note">Strongest predictor of falls</div>
                    {expandedParams.has('stride_speed_cv') && (
                      <div className="parameter-explanation">
                        <p><strong>{PARAMETER_DEFINITIONS.stride_speed_cv.description}</strong></p>
                        <p className="clinical-note">{PARAMETER_DEFINITIONS.stride_speed_cv.clinicalSignificance}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Variability Parameters */}
          {(metrics.step_length_cv !== undefined || metrics.step_time_cv !== undefined) && (
            <section className="report-section variability-parameters">
              <div className="section-header">
                <TrendingUp className="section-icon" size={24} />
                <h2>Gait Variability</h2>
              </div>
              <div className="parameters-grid">
                {metrics.step_length_cv !== undefined && (
                  <div className="parameter-card">
                    <div className="parameter-header">
                      <span className="parameter-name">Step Length Variability</span>
                      <button 
                        className="info-button"
                        onClick={() => toggleParamExplanation('step_length_cv')}
                        title="Learn more about this parameter"
                      >
                        <Info size={16} />
                      </button>
                    </div>
                    <div className="parameter-value">{metrics.step_length_cv.toFixed(2)}</div>
                    <div className="parameter-unit">% CV</div>
                    {expandedParams.has('step_length_cv') && (
                      <div className="parameter-explanation">
                        <p><strong>{PARAMETER_DEFINITIONS.step_length_cv.description}</strong></p>
                        <p className="clinical-note">{PARAMETER_DEFINITIONS.step_length_cv.clinicalSignificance}</p>
                      </div>
                    )}
                  </div>
                )}

                {metrics.step_time_cv !== undefined && (
                  <div className="parameter-card">
                    <div className="parameter-header">
                      <span className="parameter-name">Step Time Variability</span>
                      <button 
                        className="info-button"
                        onClick={() => toggleParamExplanation('step_time_cv')}
                        title="Learn more about this parameter"
                      >
                        <Info size={16} />
                      </button>
                    </div>
                    <div className="parameter-value">{metrics.step_time_cv.toFixed(2)}</div>
                    <div className="parameter-unit">% CV</div>
                    {expandedParams.has('step_time_cv') && (
                      <div className="parameter-explanation">
                        <p><strong>{PARAMETER_DEFINITIONS.step_time_cv.description}</strong></p>
                        <p className="clinical-note">{PARAMETER_DEFINITIONS.step_time_cv.clinicalSignificance}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Symmetry Parameters */}
          {(metrics.step_time_symmetry !== undefined || metrics.step_length_symmetry !== undefined) && (
            <section className="report-section symmetry-parameters">
              <div className="section-header">
                <Activity className="section-icon" size={24} />
                <h2>Gait Symmetry</h2>
              </div>
              <div className="parameters-grid">
                {metrics.step_time_symmetry !== undefined && (
                  <div className="parameter-card">
                    <div className="parameter-header">
                      <span className="parameter-name">Step Time Symmetry</span>
                      <button 
                        className="info-button"
                        onClick={() => toggleParamExplanation('step_time_symmetry')}
                        title="Learn more about this parameter"
                      >
                        <Info size={16} />
                      </button>
                    </div>
                    <div className="parameter-value">{(metrics.step_time_symmetry * 100).toFixed(1)}</div>
                    <div className="parameter-unit">%</div>
                    <div className={`parameter-status ${metrics.step_time_symmetry >= 0.85 && metrics.step_time_symmetry <= 1.15 ? 'normal' : 'warning'}`}>
                      {metrics.step_time_symmetry >= 0.85 && metrics.step_time_symmetry <= 1.15 ? '✅ Good symmetry' : '⚠️ Asymmetry detected'}
                    </div>
                    {expandedParams.has('step_time_symmetry') && (
                      <div className="parameter-explanation">
                        <p><strong>{PARAMETER_DEFINITIONS.step_time_symmetry.description}</strong></p>
                        <p className="clinical-note">{PARAMETER_DEFINITIONS.step_time_symmetry.clinicalSignificance}</p>
                      </div>
                    )}
                  </div>
                )}

                {metrics.step_length_symmetry !== undefined && (
                  <div className="parameter-card">
                    <div className="parameter-header">
                      <span className="parameter-name">Step Length Symmetry</span>
                      <button 
                        className="info-button"
                        onClick={() => toggleParamExplanation('step_length_symmetry')}
                        title="Learn more about this parameter"
                      >
                        <Info size={16} />
                      </button>
                    </div>
                    <div className="parameter-value">{(metrics.step_length_symmetry * 100).toFixed(1)}</div>
                    <div className="parameter-unit">%</div>
                    {expandedParams.has('step_length_symmetry') && (
                      <div className="parameter-explanation">
                        <p><strong>{PARAMETER_DEFINITIONS.step_length_symmetry.description}</strong></p>
                        <p className="clinical-note">{PARAMETER_DEFINITIONS.step_length_symmetry.clinicalSignificance}</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Professional Assessment Section */}
          {fallRiskAssessment.risk_level && (
            <section className="report-section assessment-section">
              <div className="section-header">
                <Shield className="section-icon" size={24} />
                <h2>Professional Assessment</h2>
              </div>
              <div className="assessment-content">
                <div className={`assessment-card risk-${fallRiskAssessment.risk_level.toLowerCase()}`}>
                  <h3>Fall Risk Assessment</h3>
                  <div className="assessment-details">
                    <div className="assessment-item">
                      <span className="assessment-label">Risk Level:</span>
                      <span className="assessment-value">{fallRiskAssessment.risk_level}</span>
                    </div>
                    <div className="assessment-item">
                      <span className="assessment-label">Risk Score:</span>
                      <span className="assessment-value">{fallRiskAssessment.risk_score?.toFixed(1) || 'N/A'}</span>
                    </div>
                    <div className="assessment-item">
                      <span className="assessment-label">Category:</span>
                      <span className="assessment-value">{fallRiskAssessment.risk_category || 'N/A'}</span>
                    </div>
                    {fallRiskAssessment.risk_factors && fallRiskAssessment.risk_factors.length > 0 && (
                      <div className="assessment-item full-width">
                        <span className="assessment-label">Key Risk Factors:</span>
                        <ul className="risk-factors-list">
                          {fallRiskAssessment.risk_factors.map((factor, idx) => (
                            <li key={idx}>{factor}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>

                {functionalMobility.mobility_level && (
                  <div className="assessment-card">
                    <h3>Functional Mobility Assessment</h3>
                    <div className="assessment-details">
                      <div className="assessment-item">
                        <span className="assessment-label">Mobility Level:</span>
                        <span className="assessment-value">{functionalMobility.mobility_level}</span>
                      </div>
                      <div className="assessment-item">
                        <span className="assessment-label">Mobility Score:</span>
                        <span className="assessment-value">{functionalMobility.mobility_score?.toFixed(1) || 'N/A'} / 100</span>
                      </div>
                      <div className="assessment-item">
                        <span className="assessment-label">Category:</span>
                        <span className="assessment-value">{functionalMobility.mobility_category || 'N/A'}</span>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Video Quality Assessment Section */}
          {(analysis.video_quality_score !== undefined || analysis.video_quality_issues || analysis.video_quality_recommendations) && (
            <section className="report-section video-quality-section">
              <div className="section-header">
                <Activity className="section-icon" size={24} />
                <h2>Video Quality Assessment</h2>
              </div>
              <div className="video-quality-content">
                {analysis.video_quality_score !== undefined && (
                  <div className={`quality-score-card ${analysis.video_quality_valid ? 'quality-good' : analysis.video_quality_score >= 60 ? 'quality-moderate' : 'quality-poor'}`}>
                    <div className="quality-score-header">
                      <span>Video Quality Score</span>
                      <span className="quality-score-value">{analysis.video_quality_score.toFixed(0)}%</span>
                    </div>
                    <div className="quality-score-status">
                      {analysis.video_quality_valid ? (
                        <span className="status-good">✅ Quality acceptable for gait analysis</span>
                      ) : analysis.video_quality_score >= 60 ? (
                        <span className="status-moderate">⚠️ Quality moderate - results may have reduced accuracy</span>
                      ) : (
                        <span className="status-poor">❌ Quality insufficient - consider re-recording video</span>
                      )}
                    </div>
                  </div>
                )}

                {analysis.pose_detection_rate !== undefined && (
                  <div className="quality-metric-item">
                    <strong>Pose Detection Rate:</strong> {(analysis.pose_detection_rate * 100).toFixed(1)}%
                    <p className="metric-note">Percentage of video frames where body pose was successfully detected</p>
                  </div>
                )}

                {analysis.video_quality_issues && analysis.video_quality_issues.length > 0 && (
                  <div className="quality-issues-list">
                    <h3>Issues Detected</h3>
                    <ul>
                      {analysis.video_quality_issues.map((issue, idx) => (
                        <li key={idx}>{issue}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {analysis.video_quality_recommendations && analysis.video_quality_recommendations.length > 0 && (
                  <div className="quality-recommendations-list">
                    <h3>💡 Tips for Better Video Quality</h3>
                    <p className="recommendations-intro">
                      For more accurate gait analysis results, consider the following recommendations when recording your next video:
                    </p>
                    <ul>
                      {analysis.video_quality_recommendations.map((rec, idx) => (
                        <li key={idx}>{rec}</li>
                      ))}
                    </ul>
                    <div className="general-tips">
                      <h4>General Recording Tips:</h4>
                      <ul>
                        <li>Record 5-10 seconds of continuous walking</li>
                        <li>Use side view for best gait parameter visibility</li>
                        <li>Ensure person walks at comfortable pace</li>
                        <li>Include at least 3-4 complete gait cycles</li>
                        <li>Record on flat, level surface</li>
                        <li>Good lighting with person clearly visible</li>
                        <li>Keep camera steady and at person's hip height</li>
                        <li>Ensure full body is visible in frame</li>
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Parameter Reference Section */}
          <section className="report-section parameter-reference">
            <div className="section-header">
              <Info className="section-icon" size={24} />
              <h2>Parameter Definitions</h2>
            </div>
            <div className="reference-content">
              <p className="reference-intro">
                Click the <Info size={14} style={{ display: 'inline', verticalAlign: 'middle' }} /> icon next to any parameter above to view its definition and clinical significance. 
                Below is a comprehensive reference for all gait analysis parameters.
              </p>
              <div className="reference-grid">
                {Object.entries(PARAMETER_DEFINITIONS).map(([key, def]) => {
                  // Format value based on parameter type (gait lab standard format)
                  const formatValue = (paramKey: string, value: any): string => {
                    if (value === undefined || value === null) return 'N/A'
                    
                    switch (paramKey) {
                      case 'walking_speed':
                      case 'step_length':
                      case 'stride_length':
                      case 'step_width_mean':
                        // Distance parameters: show in meters with 3 decimal places
                        return `${(value / 1000).toFixed(3)} m`
                      case 'cadence':
                        // Cadence: show with 1 decimal place
                        return `${value.toFixed(1)} steps/min`
                      case 'step_time':
                      case 'stance_time':
                      case 'swing_time':
                      case 'double_support_time':
                        // Time parameters: show in seconds with 3 decimal places
                        return `${value.toFixed(3)} s`
                      case 'step_width_cv':
                      case 'stride_speed_cv':
                      case 'step_length_cv':
                      case 'step_time_cv':
                        // Variability (CV): show as percentage with 2 decimal places
                        return `${value.toFixed(2)}% CV`
                      case 'walk_ratio':
                        // Walk ratio: show with 4 decimal places
                        return `${value.toFixed(4)} mm/(steps/min)`
                      case 'step_time_symmetry':
                      case 'step_length_symmetry':
                        // Symmetry: show as percentage with 1 decimal place
                        return `${(value * 100).toFixed(1)}%`
                      default:
                        return String(value)
                    }
                  }
                  
                  const value = metrics[key as keyof typeof metrics]
                  const formattedValue = formatValue(key, value)
                  
                  return (
                    <div key={key} className="reference-item">
                      <h4>
                        {def.name}
                        {value !== undefined && value !== null && (
                          <span className="reference-value">: <strong>{formattedValue}</strong></span>
                        )}
                      </h4>
                      <p>{def.description}</p>
                      <p className="clinical-significance"><strong>Clinical Significance:</strong> {def.clinicalSignificance}</p>
                    </div>
                  )
                })}
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

      {/* Source Video Section */}
      {analysis.video_url && (
        <section className="report-section source-video-section">
          <div className="section-header">
            <Activity className="section-icon" size={24} />
            <h2>Source Video</h2>
          </div>
          <div className="video-preview-container">
            <p className="video-description">
              This report is based on the following video. Click the thumbnail or button below to view the original video.
            </p>
            <div className="video-thumbnail-wrapper">
              <a 
                href={analysis.video_url} 
                target="_blank"
                rel="noopener noreferrer"
                className="video-thumbnail-link"
              >
                <div className="video-thumbnail">
                  <video 
                    src={analysis.video_url} 
                    className="thumbnail-video"
                    preload="metadata"
                    muted
                  />
                  <div className="video-play-overlay">
                    <div className="play-button">▶</div>
                    <p>Click to view original video</p>
                  </div>
                </div>
              </a>
            </div>
            <div className="video-actions">
              <a 
                href={analysis.video_url} 
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-primary"
              >
                View Full Video
              </a>
            </div>
          </div>
        </section>
      )}

      <div className="report-actions">
        <button onClick={() => navigate('/view-reports')} className="btn btn-secondary">
          View All Reports
        </button>
        <button onClick={() => navigate('/upload')} className="btn btn-primary">
          Upload New Video
        </button>
      </div>
    </div>
  )
}
