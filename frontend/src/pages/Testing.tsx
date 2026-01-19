import { useState } from 'react'
import { Upload, Play, CheckCircle, XCircle, Loader2 } from 'lucide-react'
import './Testing.css'

interface StepStatus {
  completed: boolean
  available: boolean
  running: boolean
  error?: string
  result?: any
}

export default function Testing() {
  const [file, setFile] = useState<File | null>(null)
  const [analysisId, setAnalysisId] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [steps, setSteps] = useState<Record<string, StepStatus>>({
    step1: { completed: false, available: false, running: false },
    step2: { completed: false, available: false, running: false },
    step3: { completed: false, available: false, running: false },
    step4: { completed: false, available: false, running: false }
  })
  const [statusMessage, setStatusMessage] = useState<string>('')
  const [fps, setFps] = useState<number>(30.0)
  const [viewType, setViewType] = useState<string>('front')
  const [referenceLength, setReferenceLength] = useState<string>('')

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
    }
  }

  const uploadFile = async () => {
    if (!file) return

    setUploading(true)
    setStatusMessage('Uploading test file...')

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch('/api/v1/testing/upload', {
        method: 'POST',
        body: formData
      })

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`)
      }

      const data = await response.json()
      setAnalysisId(data.analysis_id)
      setSteps({
        step1: { completed: false, available: true, running: false },
        step2: { completed: false, available: false, running: false },
        step3: { completed: false, available: false, running: false },
        step4: { completed: false, available: false, running: false }
      })
      setStatusMessage(`File uploaded successfully! Analysis ID: ${data.analysis_id}`)
    } catch (error: any) {
      setStatusMessage(`Upload failed: ${error.message}`)
    } finally {
      setUploading(false)
    }
  }

  const executeStep = async (stepNumber: number) => {
    if (!analysisId) {
      setStatusMessage('Please upload a file first')
      return
    }

    const stepKey = `step${stepNumber}` as keyof typeof steps
    setSteps(prev => ({
      ...prev,
      [stepKey]: { ...prev[stepKey], running: true, error: undefined }
    }))
    setStatusMessage(`Executing Step ${stepNumber}...`)

    try {
      let url = ''
      let params = new URLSearchParams({ analysis_id: analysisId })

      if (stepNumber === 1) {
        params.append('fps', fps.toString())
        params.append('view_type', viewType)
        url = `/api/v1/testing/step/1?${params}`
      } else if (stepNumber === 2) {
        params.append('view_type', viewType)
        url = `/api/v1/testing/step/2?${params}`
      } else if (stepNumber === 3) {
        params.append('fps', fps.toString())
        if (referenceLength) {
          params.append('reference_length_mm', referenceLength)
        }
        url = `/api/v1/testing/step/3?${params}`
      } else if (stepNumber === 4) {
        url = `/api/v1/testing/step/4?${params}`
      }

      const response = await fetch(url, { method: 'POST' })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || `Step ${stepNumber} failed`)
      }

      const data = await response.json()
      
      setSteps(prev => ({
        ...prev,
        [stepKey]: {
          completed: true,
          available: true,
          running: false,
          result: data.result
        },
        ...(stepNumber < 4 && {
          [`step${stepNumber + 1}`]: {
            ...prev[`step${stepNumber + 1}` as keyof typeof prev],
            available: true
          }
        })
      }))

      setStatusMessage(`Step ${stepNumber} completed successfully! ${data.message}`)
      
      // Refresh status
      await refreshStatus()
    } catch (error: any) {
      setSteps(prev => ({
        ...prev,
        [stepKey]: {
          ...prev[stepKey],
          running: false,
          error: error.message
        }
      }))
      setStatusMessage(`Step ${stepNumber} failed: ${error.message}`)
    }
  }

  const refreshStatus = async () => {
    if (!analysisId) return

    try {
      const response = await fetch(`/api/v1/testing/status/${analysisId}`)
      if (response.ok) {
        const data = await response.json()
        setSteps({
          step1: {
            completed: data.steps_completed?.step_1_pose_estimation || false,
            available: data.steps_available?.step_1 || false,
            running: false
          },
          step2: {
            completed: data.steps_completed?.step_2_3d_lifting || false,
            available: data.steps_available?.step_2 || false,
            running: false
          },
          step3: {
            completed: data.steps_completed?.step_3_metrics_calculation || false,
            available: data.steps_available?.step_3 || false,
            running: false
          },
          step4: {
            completed: data.steps_completed?.step_4_report_generation || false,
            available: data.steps_available?.step_4 || false,
            running: false
          }
        })
        setStatusMessage(data.step_message || '')
      }
    } catch (error) {
      console.error('Failed to refresh status:', error)
    }
  }

  return (
    <div className="testing-container">
      <div className="testing-header">
        <h1>🧪 Testing Mode - Step-by-Step Processing</h1>
        <p className="testing-subtitle">
          Upload a test file and execute each step manually. Each step's output is saved
          and can be used by subsequent steps.
        </p>
      </div>

      <div className="testing-content">
        {/* File Upload Section */}
        <div className="testing-section">
          <h2>1. Upload Test File</h2>
          <div className="upload-section">
            <input
              type="file"
              accept="video/*"
              onChange={handleFileSelect}
              disabled={uploading}
              className="file-input"
            />
            <button
              onClick={uploadFile}
              disabled={!file || uploading}
              className="btn-primary"
            >
              {uploading ? (
                <>
                  <Loader2 className="spinner" />
                  Uploading...
                </>
              ) : (
                <>
                  <Upload />
                  Upload File
                </>
              )}
            </button>
          </div>
          {analysisId && (
            <div className="analysis-info">
              <strong>Analysis ID:</strong> {analysisId}
            </div>
          )}
        </div>

        {/* Configuration Section */}
        <div className="testing-section">
          <h2>2. Configuration</h2>
          <div className="config-grid">
            <div className="config-item">
              <label>FPS:</label>
              <input
                type="number"
                value={fps}
                onChange={(e) => setFps(parseFloat(e.target.value) || 30)}
                min="1"
                max="120"
                step="0.1"
              />
            </div>
            <div className="config-item">
              <label>View Type:</label>
              <select value={viewType} onChange={(e) => setViewType(e.target.value)}>
                <option value="front">Front</option>
                <option value="side">Side</option>
              </select>
            </div>
            <div className="config-item">
              <label>
                Reference Length (mm):
                <span className="help-icon" title="Click for info">ℹ️</span>
              </label>
              <input
                type="number"
                value={referenceLength}
                onChange={(e) => setReferenceLength(e.target.value)}
                placeholder="Optional - leave empty for auto-calibration"
                min="0"
              />
              <div className="help-text">
                <strong>What is this?</strong> A known measurement in millimeters (e.g., height of a person, 
                length of a reference object in the video) used to convert pixel measurements to real-world 
                measurements. <strong>Leave empty</strong> if you don't have a reference - the system will 
                auto-calibrate using typical human proportions.
              </div>
            </div>
          </div>
        </div>

        {/* Steps Section */}
        <div className="testing-section">
          <h2>3. Execute Steps</h2>
          <div className="steps-container">
            {[1, 2, 3, 4].map((stepNum) => {
              const stepKey = `step${stepNum}` as keyof typeof steps
              const step = steps[stepKey]
              const stepNames = [
                '2D Pose Estimation',
                '3D Lifting',
                'Gait Metrics Calculation',
                'Report Generation'
              ]

              return (
                <div
                  key={stepNum}
                  className={`step-card ${step.completed ? 'completed' : ''} ${step.running ? 'running' : ''} ${!step.available ? 'disabled' : ''}`}
                >
                  <div className="step-header">
                    <div className="step-number">{stepNum}</div>
                    <div className="step-title">
                      <h3>Step {stepNum}: {stepNames[stepNum - 1]}</h3>
                    </div>
                    <div className="step-status">
                      {step.running ? (
                        <Loader2 className="spinner" />
                      ) : step.completed ? (
                        <CheckCircle className="check-icon" />
                      ) : step.error ? (
                        <XCircle className="error-icon" />
                      ) : null}
                    </div>
                  </div>
                  
                  {step.error && (
                    <div className="step-error">Error: {step.error}</div>
                  )}
                  
                  {step.result && (
                    <div className="step-result">
                      <pre>{JSON.stringify(step.result, null, 2)}</pre>
                    </div>
                  )}

                  <button
                    onClick={() => executeStep(stepNum)}
                    disabled={!step.available || step.running}
                    className={`btn-step ${!step.available ? 'btn-disabled' : ''}`}
                  >
                    {step.running ? (
                      <>
                        <Loader2 className="spinner" />
                        Processing Step {stepNum}...
                      </>
                    ) : step.completed ? (
                      <>
                        <CheckCircle />
                        Step {stepNum} Complete - Run Again
                      </>
                    ) : !step.available ? (
                      <>
                        <XCircle />
                        Step {stepNum} Not Available
                      </>
                    ) : (
                      <>
                        <Play />
                        Execute Step {stepNum}
                      </>
                    )}
                  </button>
                </div>
              )
            })}
          </div>
        </div>

        {/* Status Section */}
        {statusMessage && (
          <div className="status-section">
            <h3>Status</h3>
            <div className="status-message">{statusMessage}</div>
            {analysisId && (
              <button onClick={refreshStatus} className="btn-secondary">
                Refresh Status
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
