import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import './AnalysisUpload.css'

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
    console.log('Upload button clicked')
    
    if (!file) {
      setError('Please select a file')
      console.error('No file selected')
      return
    }

    console.log('Starting upload for file:', file.name, 'Size:', file.size, 'bytes')
    console.log('API URL:', API_URL)
    
    // First, check if backend is accessible
    try {
      console.log('Checking backend health...')
      const healthResponse = await fetch(`${API_URL}/api/v1/health`, {
        method: 'GET',
        signal: AbortSignal.timeout(10000) // 10 second timeout for health check
      })
      
      if (!healthResponse.ok) {
        throw new Error(`Backend health check failed: ${healthResponse.status}`)
      }
      console.log('✅ Backend is healthy')
    } catch (healthError: any) {
      console.error('❌ Backend health check failed:', healthError)
      setError(`Cannot connect to backend server. Please check if the backend is running.\n\nError: ${healthError.message}\n\nBackend URL: ${API_URL}`)
      setStatus('failed')
      return
    }
    
    // Set status and show progress bar immediately
    setStatus('uploading')
    setError(null)
    setProgress(1) // Show progress bar immediately (1% so it's visible)

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('view_type', 'front')

      console.log('Creating XHR request...')
      const xhr = new XMLHttpRequest()

      let lastProgressUpdate = Date.now()
      let progressCheckInterval: number | null = null

      // Progress event handler
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable && e.total > 0) {
          const percentComplete = (e.loaded / e.total) * 100
          const elapsed = Date.now() - lastProgressUpdate
          console.log(`Upload progress: ${percentComplete.toFixed(1)}% (${(e.loaded / 1024 / 1024).toFixed(2)} MB / ${(e.total / 1024 / 1024).toFixed(2)} MB) - ${(elapsed / 1000).toFixed(1)}s since last update`)
          setProgress(Math.max(percentComplete, 1)) // Ensure at least 1% is shown
          lastProgressUpdate = Date.now()
        } else {
          // If length not computable, show indeterminate progress
          console.log('Upload in progress (size unknown)')
          // Don't set progress to 50% here - let it stay at 5% until we get real progress
        }
      })

      // Load start - show progress immediately
      xhr.upload.addEventListener('loadstart', () => {
        console.log('Upload started - connection established')
        setProgress(5) // Show 5% immediately when upload starts
        lastProgressUpdate = Date.now()
        
        // Monitor for stuck uploads - if no progress for 30 seconds, show warning
        progressCheckInterval = setInterval(() => {
          const timeSinceLastProgress = Date.now() - lastProgressUpdate
          if (timeSinceLastProgress > 30000 && progress < 10) {
            console.warn('⚠️ Upload appears stuck - no progress for 30 seconds')
            setError('Upload appears to be stuck. The backend may be processing a large file. Please wait or try again with a smaller file.')
          }
        }, 5000) // Check every 5 seconds
      })

      const uploadPromise = new Promise<string>((resolve, reject) => {
        xhr.onload = () => {
          if (progressCheckInterval) {
            clearInterval(progressCheckInterval)
          }
          console.log('Upload response received. Status:', xhr.status)
          if (xhr.status === 200) {
            try {
              const response = JSON.parse(xhr.responseText)
              console.log('Upload successful. Analysis ID:', response.analysis_id)
              resolve(response.analysis_id)
            } catch (parseError) {
              console.error('Failed to parse response:', parseError)
              reject(new Error('Invalid response from server'))
            }
          } else {
            console.error('Upload failed with status:', xhr.status, xhr.statusText)
            let errorMessage = `Upload failed: ${xhr.status} ${xhr.statusText}`
            try {
              const errorData = JSON.parse(xhr.responseText)
              if (errorData.detail) {
                errorMessage += ` - ${errorData.detail}`
              }
            } catch (e) {
              // Ignore parse errors
            }
            reject(new Error(errorMessage))
          }
        }

        xhr.onerror = () => {
          if (progressCheckInterval) {
            clearInterval(progressCheckInterval)
          }
          console.error('Upload network error - XHR onerror fired')
          console.error('Response status:', xhr.status)
          console.error('Response text:', xhr.responseText)
          reject(new Error(`Network error - Cannot connect to server. Please check:\n1. Backend is running at ${API_URL}\n2. CORS is configured correctly\n3. Network connection is stable`))
        }

        xhr.ontimeout = () => {
          if (progressCheckInterval) {
            clearInterval(progressCheckInterval)
          }
          console.error('Upload timeout after 10 minutes')
          reject(new Error(`Upload timeout - Server took too long to respond (10 minutes).\n\nThis may happen with very large files. The backend is processing your file, but it's taking longer than expected.\n\nFile size: ${(file.size / 1024 / 1024).toFixed(2)} MB\n\nPlease try:\n1. Wait a few more minutes\n2. Try with a smaller file\n3. Check backend logs for processing status`))
        }

        xhr.onabort = () => {
          if (progressCheckInterval) {
            clearInterval(progressCheckInterval)
          }
          console.error('Upload aborted')
          reject(new Error('Upload was cancelled'))
        }

        console.log('Opening XHR connection to:', `${API_URL}/api/v1/analysis/upload`)
        xhr.open('POST', `${API_URL}/api/v1/analysis/upload`)
        xhr.timeout = 600000 // 10 minutes timeout for large files (increased from 5 minutes)
        xhr.send(formData)
      })

      const id = await uploadPromise
      console.log('Upload complete. Analysis ID:', id)
      setAnalysisId(id)
      setProgress(100)
      setStatus('processing')
      setCurrentStep('pose_estimation')

      // Poll for analysis status
      pollAnalysisStatus(id)
    } catch (err: any) {
      console.error('Upload error:', err)
      setError(err.message || 'Upload failed. Please try again.')
      setStatus('failed')
      setProgress(0)
    }
  }

  const pollAnalysisStatus = async (id: string) => {
    const poll = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/analysis/${id}`)
        
        if (!response.ok) {
          throw new Error(`Failed to fetch analysis status: ${response.statusText}`)
        }

        const data = await response.json()
        const analysisStatus = data.status

        // Use real progress data from backend
        if (analysisStatus === 'processing') {
          // Update with real backend progress
          const backendStep = data.current_step || 'pose_estimation'
          const backendProgress = data.step_progress || 0
          const backendMessage = data.step_message || 'Processing...'
          
          // Map backend step names to frontend step types
          const stepMapping: Record<string, ProcessingStep> = {
            'pose_estimation': 'pose_estimation',
            '3d_lifting': '3d_lifting',
            'metrics_calculation': 'metrics_calculation',
            'report_generation': 'report_generation'
          }
          
          const mappedStep = stepMapping[backendStep] || 'pose_estimation'
          setCurrentStep(mappedStep)
          setStepProgress(backendProgress)
          setStepMessage(backendMessage)
          
          console.log(`Progress update: ${backendStep} - ${backendProgress}% - ${backendMessage}`)
          
          // Continue polling - more frequent during processing for better UX
          setTimeout(poll, 1000) // Poll every 1 second for real-time updates (Apple-style responsiveness)
        } else if (analysisStatus === 'completed') {
          setStatus('completed')
          setCurrentStep('report_generation')
          setStepProgress(data.step_progress || 100)
          setStepMessage(data.step_message || 'Analysis complete! Reports ready.')
        } else if (analysisStatus === 'failed') {
          setStatus('failed')
          setError(data.error || 'Analysis failed')
          setStepProgress(0)
          setStepMessage(data.step_message || 'Analysis failed')
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
          <div className="processing-details apple-style">
            <div className="processing-header">
              <h3>Analyzing Your Video</h3>
              <p className="processing-subtitle">This may take a few minutes. We'll keep you updated.</p>
            </div>
            
            {/* Overall Progress Indicator */}
            {currentStep && (
              <div className="overall-progress-card">
                <div className="overall-progress-header">
                  <span className="current-step-label">
                    {currentStep === 'pose_estimation' && 'Step 1 of 4'}
                    {currentStep === '3d_lifting' && 'Step 2 of 4'}
                    {currentStep === 'metrics_calculation' && 'Step 3 of 4'}
                    {currentStep === 'report_generation' && 'Step 4 of 4'}
                  </span>
                  <span className="overall-progress-percent">{stepProgress}%</span>
                </div>
                <div className="overall-progress-bar-container">
                  <div 
                    className="overall-progress-bar" 
                    style={{ width: `${stepProgress}%` }}
                  ></div>
                </div>
                <p className="overall-progress-message">
                  {stepMessage || `Processing ${currentStep.replace('_', ' ')}...`}
                </p>
              </div>
            )}

            <div className="processing-steps apple-steps">
              <div className={`step-card ${currentStep === 'pose_estimation' ? 'active' : currentStep && ['3d_lifting', 'metrics_calculation', 'report_generation'].includes(currentStep) ? 'completed' : 'pending'}`}>
                <div className="step-indicator">
                  {currentStep && ['3d_lifting', 'metrics_calculation', 'report_generation'].includes(currentStep) ? (
                    <div className="step-checkmark">✓</div>
                  ) : currentStep === 'pose_estimation' ? (
                    <div className="step-spinner">
                      <Loader2 className="spinner-icon" />
                    </div>
                  ) : (
                    <div className="step-number">1</div>
                  )}
                </div>
                <div className="step-content">
                  <div className="step-title">Pose Estimation</div>
                  <div className="step-description">
                    {currentStep === 'pose_estimation' ? stepMessage || 'Extracting 2D keypoints from video frames...' : 'Extracting 2D keypoints from video'}
                  </div>
                  {currentStep === 'pose_estimation' && stepProgress > 0 && (
                    <div className="step-progress-indicator">
                      <div className="step-progress-track">
                        <div className="step-progress-fill" style={{ width: `${stepProgress}%` }}></div>
                      </div>
                      <span className="step-progress-text">{stepProgress}%</span>
                    </div>
                  )}
                </div>
              </div>
              
              <div className={`step-card ${currentStep === '3d_lifting' ? 'active' : currentStep && ['metrics_calculation', 'report_generation'].includes(currentStep) ? 'completed' : 'pending'}`}>
                <div className="step-indicator">
                  {currentStep && ['metrics_calculation', 'report_generation'].includes(currentStep) ? (
                    <div className="step-checkmark">✓</div>
                  ) : currentStep === '3d_lifting' ? (
                    <div className="step-spinner">
                      <Loader2 className="spinner-icon" />
                    </div>
                  ) : (
                    <div className="step-number">2</div>
                  )}
                </div>
                <div className="step-content">
                  <div className="step-title">3D Lifting</div>
                  <div className="step-description">
                    {currentStep === '3d_lifting' ? stepMessage || 'Converting 2D keypoints to 3D space...' : 'Converting to 3D pose'}
                  </div>
                  {currentStep === '3d_lifting' && stepProgress > 0 && (
                    <div className="step-progress-indicator">
                      <div className="step-progress-track">
                        <div className="step-progress-fill" style={{ width: `${stepProgress}%` }}></div>
                      </div>
                      <span className="step-progress-text">{stepProgress}%</span>
                    </div>
                  )}
                </div>
              </div>
              
              <div className={`step-card ${currentStep === 'metrics_calculation' ? 'active' : currentStep === 'report_generation' ? 'completed' : 'pending'}`}>
                <div className="step-indicator">
                  {currentStep === 'report_generation' ? (
                    <div className="step-checkmark">✓</div>
                  ) : currentStep === 'metrics_calculation' ? (
                    <div className="step-spinner">
                      <Loader2 className="spinner-icon" />
                    </div>
                  ) : (
                    <div className="step-number">3</div>
                  )}
                </div>
                <div className="step-content">
                  <div className="step-title">Metrics Calculation</div>
                  <div className="step-description">
                    {currentStep === 'metrics_calculation' ? stepMessage || 'Computing gait metrics and patterns...' : 'Computing gait metrics'}
                  </div>
                  {currentStep === 'metrics_calculation' && stepProgress > 0 && (
                    <div className="step-progress-indicator">
                      <div className="step-progress-track">
                        <div className="step-progress-fill" style={{ width: `${stepProgress}%` }}></div>
                      </div>
                      <span className="step-progress-text">{stepProgress}%</span>
                    </div>
                  )}
                </div>
              </div>
              
              <div className={`step-card ${currentStep === 'report_generation' ? 'active' : 'pending'}`}>
                <div className="step-indicator">
                  {currentStep === 'report_generation' ? (
                    <div className="step-spinner">
                      <Loader2 className="spinner-icon" />
                    </div>
                  ) : (
                    <div className="step-number">4</div>
                  )}
                </div>
                <div className="step-content">
                  <div className="step-title">Report Generation</div>
                  <div className="step-description">
                    {currentStep === 'report_generation' ? stepMessage || 'Generating detailed analysis reports...' : 'Generating analysis reports'}
                  </div>
                  {currentStep === 'report_generation' && stepProgress > 0 && (
                    <div className="step-progress-indicator">
                      <div className="step-progress-track">
                        <div className="step-progress-fill" style={{ width: `${stepProgress}%` }}></div>
                      </div>
                      <span className="step-progress-text">{stepProgress}%</span>
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
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            console.log('Upload button clicked, file:', file?.name, 'Status:', status)
            if (file && status !== 'uploading' && status !== 'processing') {
              handleUpload()
            } else {
              console.warn('Upload prevented - file:', file, 'status:', status)
            }
          }}
          disabled={!file || status === 'uploading' || status === 'processing'}
          className="btn btn-primary"
          style={{ 
            marginTop: '1rem',
            cursor: (!file || status === 'uploading' || status === 'processing') ? 'not-allowed' : 'pointer',
            opacity: (!file || status === 'uploading' || status === 'processing') ? 0.6 : 1
          }}
        >
          {status === 'uploading' ? `Uploading... ${Math.round(progress)}%` : status === 'processing' ? 'Processing...' : 'Upload and Analyze'}
        </button>
      </div>
    </div>
  )
}
