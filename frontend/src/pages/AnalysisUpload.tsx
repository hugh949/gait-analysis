import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import './AnalysisUpload.css'

const getApiUrl = () => {
  if (typeof window !== 'undefined' && window.location.hostname.includes('azurestaticapps.net')) {
    return 'https://gait-analysis-api-simple.azurewebsites.net'
  }
  return (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000'
}

const API_URL = getApiUrl()

type UploadStatus = 'idle' | 'uploading' | 'processing' | 'completed' | 'failed'

type ProcessingStep = 'pose_estimation' | '3d_lifting' | 'metrics_calculation' | 'report_generation'

export default function AnalysisUpload() {
  const [file, setFile] = useState<File | null>(null)
  const [status, setStatus] = useState<UploadStatus>('idle')
  const [analysisId, setAnalysisId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)
  const [currentStep, setCurrentStep] = useState<ProcessingStep | null>(null)
  const navigate = useNavigate()

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0])
      setError(null)
    }
  }

  const handleUpload = async () => {
    if (!file) {
      setError('Please select a file')
      return
    }

    setStatus('uploading')
    setError(null)
    setProgress(0)

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('view_type', 'front')

      const xhr = new XMLHttpRequest()

      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const percentComplete = (e.loaded / e.total) * 100
          setProgress(percentComplete)
        }
      })

      const uploadPromise = new Promise<string>((resolve, reject) => {
        xhr.onload = () => {
          if (xhr.status === 200) {
            const response = JSON.parse(xhr.responseText)
            resolve(response.analysis_id)
          } else {
            reject(new Error(`Upload failed: ${xhr.statusText}`))
          }
        }

        xhr.onerror = () => {
          reject(new Error('Network error'))
        }

        xhr.open('POST', `${API_URL}/api/v1/analysis/upload`)
        xhr.send(formData)
      })

      const id = await uploadPromise
      setAnalysisId(id)
      setProgress(100)
      setStatus('processing')
      setCurrentStep('pose_estimation')

      // Poll for analysis status
      pollAnalysisStatus(id)
    } catch (err: any) {
      setError(err.message || 'Upload failed. Please try again.')
      setStatus('failed')
      setProgress(0)
    }
  }

  const pollAnalysisStatus = async (id: string) => {
    const steps: ProcessingStep[] = ['pose_estimation', '3d_lifting', 'metrics_calculation', 'report_generation']
    let stepIndex = 0

    const poll = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/analysis/${id}`)
        
        if (!response.ok) {
          throw new Error(`Failed to fetch analysis status: ${response.statusText}`)
        }

        const data = await response.json()
        const analysisStatus = data.status

        // Update current step (simulate progression)
        if (stepIndex < steps.length - 1) {
          setCurrentStep(steps[stepIndex])
          stepIndex++
        } else {
          setCurrentStep(steps[steps.length - 1])
        }

        if (analysisStatus === 'completed') {
          setStatus('completed')
          setCurrentStep('report_generation')
        } else if (analysisStatus === 'failed') {
          setStatus('failed')
          setError(data.error || 'Analysis failed')
        } else if (analysisStatus === 'processing') {
          // Continue polling
          setTimeout(poll, 5000) // Poll every 5 seconds
        }
      } catch (err: any) {
        console.error('Polling error:', err)
        // Continue polling on error (analysis might still be processing)
        setTimeout(poll, 5000)
      }
    }

    // Start polling
    poll()
  }

  return (
    <div className="upload-page">
      <h2>Upload Video</h2>
      <p className="description">
        Upload a video file for gait analysis. Supported formats: MP4, AVI, MOV, MKV
      </p>

      <div className="upload-section">
        <input
          type="file"
          accept="video/*"
          onChange={handleFileChange}
          disabled={status === 'uploading' || status === 'processing'}
          className="file-input"
        />

        {file && (
          <div className="file-info">
            <p><strong>Selected file:</strong> {file.name}</p>
            <p><strong>Size:</strong> {(file.size / (1024 * 1024)).toFixed(2)} MB</p>
            <p><strong>Type:</strong> {file.type}</p>
          </div>
        )}

        {error && (
          <div className="error">
            {error}
          </div>
        )}

        {status === 'uploading' && progress > 0 && (
          <div className="progress-container">
            <div className="progress-bar-wrapper">
              <div
                className="progress-bar"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="progress-text">Uploading... {Math.round(progress)}%</p>
          </div>
        )}

        {status === 'processing' && (
          <div className="processing-details">
            <h3>Processing Video Analysis</h3>
            <div className="processing-steps">
              <div className={`step ${currentStep === 'pose_estimation' ? 'active' : currentStep && ['3d_lifting', 'metrics_calculation', 'report_generation'].includes(currentStep) ? 'completed' : ''}`}>
                <div className="step-number">{currentStep && ['3d_lifting', 'metrics_calculation', 'report_generation'].includes(currentStep) ? '✓' : currentStep === 'pose_estimation' ? <Loader2 className="spinner" /> : '1'}</div>
                <div className="step-content">
                  <div className="step-title">Pose Estimation</div>
                  <div className="step-description">Extracting 2D keypoints from video</div>
                </div>
              </div>
              <div className={`step ${currentStep === '3d_lifting' ? 'active' : currentStep && ['metrics_calculation', 'report_generation'].includes(currentStep) ? 'completed' : ''}`}>
                <div className="step-number">{currentStep && ['metrics_calculation', 'report_generation'].includes(currentStep) ? '✓' : currentStep === '3d_lifting' ? <Loader2 className="spinner" /> : '2'}</div>
                <div className="step-content">
                  <div className="step-title">3D Lifting</div>
                  <div className="step-description">Converting to 3D pose</div>
                </div>
              </div>
              <div className={`step ${currentStep === 'metrics_calculation' ? 'active' : currentStep === 'report_generation' ? 'completed' : ''}`}>
                <div className="step-number">{currentStep === 'report_generation' ? '✓' : currentStep === 'metrics_calculation' ? <Loader2 className="spinner" /> : '3'}</div>
                <div className="step-content">
                  <div className="step-title">Metrics Calculation</div>
                  <div className="step-description">Computing gait metrics</div>
                </div>
              </div>
              <div className={`step ${currentStep === 'report_generation' ? 'active' : status === 'completed' ? 'completed' : ''}`}>
                <div className="step-number">{status === 'completed' ? '✓' : currentStep === 'report_generation' ? <Loader2 className="spinner" /> : '4'}</div>
                <div className="step-content">
                  <div className="step-title">Report Generation</div>
                  <div className="step-description">Generating analysis reports</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {status === 'completed' && analysisId && (
          <div className="completion-message">
            <h3>✅ Analysis Complete!</h3>
            <p>Your gait analysis is ready. View the reports tailored for different audiences:</p>
            <div className="dashboard-links">
              <p><strong>Analysis ID:</strong> <code>{analysisId}</code></p>
              <div className="dashboard-buttons">
                <button onClick={() => navigate(`/medical?analysisId=${analysisId}`)} className="btn btn-secondary">
                  View Medical Report
                </button>
                <button onClick={() => navigate(`/caregiver?analysisId=${analysisId}`)} className="btn btn-secondary">
                  View Caregiver Report
                </button>
                <button onClick={() => navigate(`/older-adult?analysisId=${analysisId}`)} className="btn btn-secondary">
                  View Your Report
                </button>
              </div>
              <p className="note">You can use the Analysis ID to access these reports later.</p>
            </div>
          </div>
        )}

        <button
          onClick={handleUpload}
          disabled={!file || status === 'uploading' || status === 'processing'}
          className="btn btn-primary"
          style={{ marginTop: '1rem' }}
        >
          {status === 'uploading' ? 'Uploading...' : status === 'processing' ? 'Processing...' : 'Upload and Analyze'}
        </button>
      </div>
    </div>
  )
}
