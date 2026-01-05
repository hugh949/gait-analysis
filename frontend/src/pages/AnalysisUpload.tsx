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
  const [stepProgress, setStepProgress] = useState<number>(0)
  const [stepMessage, setStepMessage] = useState<string>('')
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
    const stepMessages: Record<ProcessingStep, string[]> = {
      'pose_estimation': [
        'Initializing pose estimation model...',
        'Loading video frames...',
        'Extracting 2D keypoints from frames...',
        'Processing frame batches...',
        'Refining keypoint detections...',
        'Pose estimation complete'
      ],
      '3d_lifting': [
        'Initializing 3D lifting model...',
        'Processing temporal sequences...',
        'Converting 2D to 3D coordinates...',
        'Applying temporal smoothing...',
        'Validating 3D pose consistency...',
        '3D lifting complete'
      ],
      'metrics_calculation': [
        'Detecting gait events...',
        'Calculating spatiotemporal parameters...',
        'Computing joint kinematics...',
        'Analyzing gait patterns...',
        'Generating clinical metrics...',
        'Metrics calculation complete'
      ],
      'report_generation': [
        'Compiling analysis results...',
        'Generating medical report...',
        'Creating caregiver summary...',
        'Preparing patient-friendly report...',
        'Finalizing reports...',
        'Report generation complete'
      ]
    }
    
    let stepIndex = 0
    let messageIndex = 0
    let pollCount = 0

    const poll = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/analysis/${id}`)
        
        if (!response.ok) {
          throw new Error(`Failed to fetch analysis status: ${response.statusText}`)
        }

        const data = await response.json()
        const analysisStatus = data.status

        // Update current step and progress
        if (stepIndex < steps.length) {
          const currentStepType = steps[stepIndex]
          setCurrentStep(currentStepType)
          
          // Update step progress and message
          pollCount++
          const messages = stepMessages[currentStepType]
          const progressIncrement = 100 / (messages.length * 2) // Slower progression
          const newProgress = Math.min(95, (pollCount * progressIncrement) % 100)
          
          // Cycle through messages for current step
          messageIndex = Math.floor((pollCount / 2) % messages.length)
          setStepMessage(messages[messageIndex])
          setStepProgress(newProgress)
          
          // Move to next step after showing all messages
          if (messageIndex === messages.length - 1 && pollCount % (messages.length * 2) === 0) {
            stepIndex++
            messageIndex = 0
            setStepProgress(0)
          }
        }

        if (analysisStatus === 'completed') {
          setStatus('completed')
          setCurrentStep('report_generation')
          setStepProgress(100)
          setStepMessage('Analysis complete! Reports ready.')
        } else if (analysisStatus === 'failed') {
          setStatus('failed')
          setError(data.error || 'Analysis failed')
          setStepProgress(0)
          setStepMessage('')
        } else if (analysisStatus === 'processing') {
          // Continue polling
          setTimeout(poll, 3000) // Poll every 3 seconds for more frequent updates
        }
      } catch (err: any) {
        console.error('Polling error:', err)
        // Continue polling on error (analysis might still be processing)
        setTimeout(poll, 3000)
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

        {status === 'uploading' && (
          <div className="progress-container">
            <div className="progress-bar-wrapper">
              <div
                className="progress-bar"
                style={{ width: `${Math.max(progress, 1)}%` }}
              />
            </div>
            <p className="progress-text">
              {progress > 0 ? `Uploading... ${Math.round(progress)}%` : 'Preparing upload...'}
            </p>
          </div>
        )}

        {status === 'processing' && (
          <div className="processing-details">
            <h3>Processing Video Analysis</h3>
            
            {/* Current Step Progress */}
            {currentStep && (
              <div className="current-step-progress">
                <div className="step-progress-bar-wrapper">
                  <div 
                    className="step-progress-bar" 
                    style={{ width: `${stepProgress}%` }}
                  ></div>
                </div>
                <p className="step-progress-message">
                  {stepMessage || `Processing ${currentStep.replace('_', ' ')}...`}
                </p>
              </div>
            )}

            <div className="processing-steps">
              <div className={`step ${currentStep === 'pose_estimation' ? 'active' : currentStep && ['3d_lifting', 'metrics_calculation', 'report_generation'].includes(currentStep) ? 'completed' : ''}`}>
                <div className="step-number">{currentStep && ['3d_lifting', 'metrics_calculation', 'report_generation'].includes(currentStep) ? '✓' : currentStep === 'pose_estimation' ? <Loader2 className="spinner" /> : '1'}</div>
                <div className="step-content">
                  <div className="step-title">Pose Estimation</div>
                  <div className="step-description">
                    {currentStep === 'pose_estimation' ? stepMessage || 'Extracting 2D keypoints from video...' : 'Extracting 2D keypoints from video'}
                  </div>
                  {currentStep === 'pose_estimation' && stepProgress > 0 && (
                    <div className="step-inline-progress">
                      <div className="step-inline-bar" style={{ width: `${stepProgress}%` }}></div>
                    </div>
                  )}
                </div>
              </div>
              <div className={`step ${currentStep === '3d_lifting' ? 'active' : currentStep && ['metrics_calculation', 'report_generation'].includes(currentStep) ? 'completed' : ''}`}>
                <div className="step-number">{currentStep && ['metrics_calculation', 'report_generation'].includes(currentStep) ? '✓' : currentStep === '3d_lifting' ? <Loader2 className="spinner" /> : '2'}</div>
                <div className="step-content">
                  <div className="step-title">3D Lifting</div>
                  <div className="step-description">
                    {currentStep === '3d_lifting' ? stepMessage || 'Converting to 3D pose...' : 'Converting to 3D pose'}
                  </div>
                  {currentStep === '3d_lifting' && stepProgress > 0 && (
                    <div className="step-inline-progress">
                      <div className="step-inline-bar" style={{ width: `${stepProgress}%` }}></div>
                    </div>
                  )}
                </div>
              </div>
              <div className={`step ${currentStep === 'metrics_calculation' ? 'active' : currentStep === 'report_generation' ? 'completed' : ''}`}>
                <div className="step-number">{currentStep === 'report_generation' ? '✓' : currentStep === 'metrics_calculation' ? <Loader2 className="spinner" /> : '3'}</div>
                <div className="step-content">
                  <div className="step-title">Metrics Calculation</div>
                  <div className="step-description">
                    {currentStep === 'metrics_calculation' ? stepMessage || 'Computing gait metrics...' : 'Computing gait metrics'}
                  </div>
                  {currentStep === 'metrics_calculation' && stepProgress > 0 && (
                    <div className="step-inline-progress">
                      <div className="step-inline-bar" style={{ width: `${stepProgress}%` }}></div>
                    </div>
                  )}
                </div>
              </div>
              <div className={`step ${currentStep === 'report_generation' ? 'active' : ''}`}>
                <div className="step-number">{currentStep === 'report_generation' ? <Loader2 className="spinner" /> : '4'}</div>
                <div className="step-content">
                  <div className="step-title">Report Generation</div>
                  <div className="step-description">
                    {currentStep === 'report_generation' ? stepMessage || 'Generating analysis reports...' : 'Generating analysis reports'}
                  </div>
                  {currentStep === 'report_generation' && stepProgress > 0 && (
                    <div className="step-inline-progress">
                      <div className="step-inline-bar" style={{ width: `${stepProgress}%` }}></div>
                    </div>
                  )}
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
