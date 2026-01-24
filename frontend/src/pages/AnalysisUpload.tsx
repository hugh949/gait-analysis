import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, X } from 'lucide-react'
import './AnalysisUpload.css'

const getApiUrl = () => {
  // If running on same domain as backend (integrated deployment), use relative URLs
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname
    const origin = window.location.origin
    
    // Integrated app - frontend and backend on same domain
    if (hostname.includes('azurewebsites.net') || hostname.includes('localhost')) {
      console.log(`[API URL] Using relative URLs (same origin: ${origin})`)
      return '' // Use relative URLs - same origin
    }
    // Separate frontend deployment (if using Static Web Apps)
    if (hostname.includes('azurestaticapps.net')) {
      console.log(`[API URL] Using absolute URL for Static Web Apps`)
      return 'https://gaitanalysisapp.azurewebsites.net'
    }
  }
  // Development fallback
  const devUrl = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000'
  console.log(`[API URL] Using development URL: ${devUrl}`)
  return devUrl
}

const API_URL = getApiUrl()
console.log(`[API URL] Final API_URL: "${API_URL}" (empty = relative, non-empty = absolute)`)

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
  const [videoQuality, setVideoQuality] = useState<{
    score: number | null
    isValid: boolean | null
    issues: string[]
    recommendations: string[]
    poseDetectionRate: number | null
  } | null>(null)
  const [processingFrameRate, setProcessingFrameRate] = useState<number | null>(null) // Will be set from video
  const [videoFPS, setVideoFPS] = useState<number | null>(null) // Actual video FPS
  const navigate = useNavigate()
  const xhrRef = useRef<XMLHttpRequest | null>(null)
  const pollTimeoutRef = useRef<number | null>(null) // setTimeout ID for any scheduled poll (including retries)
  const progressRef = useRef<number>(0)
  const lastIndeterminateProgressRef = useRef<number>(0) // throttle indeterminate updates
  const [startTime] = useState<number>(Date.now())

  const clearPollTimeout = () => {
    if (pollTimeoutRef.current != null) {
      window.clearTimeout(pollTimeoutRef.current)
      pollTimeoutRef.current = null
    }
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      // Check if there's already a video processing
      if (status === 'uploading' || status === 'processing') {
        setError('Please wait for the current video to finish processing before uploading a new one.')
        e.target.value = '' // Clear the input
        return
      }
      const selectedFile = e.target.files[0]
      setFile(selectedFile)
      setError(null)
      
      // Extract video FPS to use as default processing rate
      // Note: Browser API doesn't directly expose FPS, so we'll let backend detect it
      // For now, set a reasonable default and let user choose
      // Backend will use actual video FPS for processing
      setVideoFPS(null) // Will be detected by backend
      setProcessingFrameRate(15) // Default to balanced 15 fps - user can change
    }
  }

  const handleUpload = async () => {
    console.log('Upload button clicked')
    
    // Ensure only one video processes at a time
    if (status === 'uploading' || status === 'processing') {
      setError('A video is already being processed. Please wait for it to complete or cancel it first.')
      return
    }
    
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
    progressRef.current = 1 // Update ref
    setProgress(1) // Show progress bar immediately (1% so it's visible)

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('view_type', 'front')
      // Add processing frame rate if user selected one, otherwise let backend auto-detect
      if (processingFrameRate !== null) {
        formData.append('processing_fps', processingFrameRate.toString())
      }

      console.log('Creating XHR request...')
      const xhr = new XMLHttpRequest()

      // Progress event handler
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable && e.total > 0) {
          const percentComplete = (e.loaded / e.total) * 100
          const newProgress = Math.max(percentComplete, 1)
          progressRef.current = newProgress
          setProgress(newProgress)
        } else {
          // Length not computable: throttle updates to once per 400ms, ramp up to 50%
          const now = Date.now()
          if (now - lastIndeterminateProgressRef.current >= 400) {
            lastIndeterminateProgressRef.current = now
            const current = progressRef.current
            if (current < 50) {
              const next = Math.min(current + 2, 50)
              progressRef.current = next
              setProgress(next)
            }
          }
        }
      })

      xhr.upload.addEventListener('loadstart', () => {
        progressRef.current = 5
        setProgress(5)
        lastIndeterminateProgressRef.current = Date.now()
      })

      const uploadPromise = new Promise<string>((resolve, reject) => {
        xhr.onload = () => {
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
            console.error('Response text:', xhr.responseText)
            
            // Try to extract detailed error from response
            let errorMessage = `Upload failed: ${xhr.status} ${xhr.statusText}`
            
            // Handle specific HTTP status codes with helpful messages
            if (xhr.status === 502) {
              // Try to extract more details from response
              let details = ''
              try {
                const response = JSON.parse(xhr.responseText)
                if (response.detail) {
                  if (typeof response.detail === 'string') {
                    details = `\n\nServer details: ${response.detail}`
                  } else if (response.detail.message) {
                    details = `\n\nServer details: ${response.detail.message}`
                  }
                }
              } catch (e) {
                // Response not JSON, ignore
              }
              
              errorMessage = `Upload failed: Server Error (502 Bad Gateway)${details}\n\n` +
                `The backend server is temporarily unavailable. This usually means:\n\n` +
                `• The server is restarting or deploying\n` +
                `• The server is overloaded\n` +
                `• There's a network/proxy issue\n` +
                `• The request timed out (file may be too large)\n\n` +
                `Please try:\n` +
                `1. Wait 30-60 seconds and try again\n` +
                `2. Check if the server is running\n` +
                `3. Try with a smaller file (<50 MB) if the issue persists\n` +
                `4. Check the browser console for more details`
            } else if (xhr.status === 500) {
              errorMessage = `Upload failed: Internal Server Error (500)\n\n` +
                `The server encountered an error processing your upload.\n\n` +
                `Please try:\n` +
                `1. Wait a moment and try again\n` +
                `2. Try with a smaller file (<50 MB)\n` +
                `3. Check the file format (MP4, AVI, MOV, MKV)`
            } else if (xhr.status === 503) {
              errorMessage = `Upload failed: Service Unavailable (503)\n\n` +
                `The service is temporarily unavailable.\n\n` +
                `Please wait a few moments and try again.`
            } else {
              // Try to parse error details from response
              try {
                const response = JSON.parse(xhr.responseText)
                if (response.detail) {
                  if (typeof response.detail === 'string') {
                    errorMessage = `Upload failed: ${xhr.status} - ${response.detail}`
                  } else if (response.detail.message) {
                    errorMessage = `Upload failed: ${xhr.status} - ${response.detail.message}`
                    if (response.detail.details) {
                      errorMessage += `\n\nDetails: ${JSON.stringify(response.detail.details, null, 2)}`
                    }
                  } else if (response.detail.error) {
                    errorMessage = `Upload failed: ${xhr.status} - ${response.detail.error}: ${response.detail.message || 'Unknown error'}`
                  }
                }
              } catch (e) {
                // If response isn't JSON, use the raw text if available
                if (xhr.responseText && xhr.responseText.length > 0) {
                  errorMessage = `Upload failed: ${xhr.status} - ${xhr.responseText.substring(0, 500)}`
                }
              }
            }
            
            reject(new Error(errorMessage))
          }
        }

        xhr.onerror = () => {
          const actualUrl = API_URL === '' ? window.location.origin : API_URL
          const fullUrl = `${actualUrl}/api/v1/analysis/upload`
          
          console.error('Upload network error - XHR onerror fired')
          console.error('XHR readyState:', xhr.readyState)
          console.error('XHR status:', xhr.status)
          console.error('XHR statusText:', xhr.statusText)
          console.error('Request URL:', fullUrl)
          console.error('API_URL:', API_URL)
          console.error('Window origin:', window.location.origin)
          console.error('Window hostname:', window.location.hostname)
          
          // Determine error type
          let errorType = 'Unknown network error'
          if (xhr.readyState === 0) {
            errorType = 'Request not sent (network/CORS issue)'
          } else if (xhr.status === 0) {
            errorType = 'Request failed (network/CORS/timeout)'
          } else if (xhr.status >= 400) {
            errorType = `HTTP error: ${xhr.status} ${xhr.statusText}`
          }
          
          // Provide more helpful error message
          let errorMsg = `Network error - ${errorType}\n\n`
          errorMsg += `Request URL: ${fullUrl}\n`
          errorMsg += `Current page: ${window.location.href}\n\n`
          
          if (API_URL === '') {
            errorMsg += `Using relative URLs (same origin).\n`
          } else {
            errorMsg += `Using absolute URL: ${API_URL}\n`
          }
          
          errorMsg += `\nPossible causes:\n`
          errorMsg += `1. Server is restarting (check logs)\n`
          errorMsg += `2. CORS configuration issue\n`
          errorMsg += `3. Network connectivity problem\n`
          errorMsg += `4. Request timeout (file too large?)\n\n`
          errorMsg += `Please try:\n`
          errorMsg += `- Wait a few seconds and try again\n`
          errorMsg += `- Check browser console for more details\n`
          errorMsg += `- Try with a smaller file if timeout occurred`
          
          reject(new Error(errorMsg))
        }

        xhr.ontimeout = () => {
          console.error('Upload timeout after 10 minutes')
          reject(new Error(`Upload timeout (10 minutes). The server may still be processing your file.\n\nFile size: ${(file.size / 1024 / 1024).toFixed(2)} MB.\n\nTry: 1) Check "View Reports" – upload may have succeeded. 2) Use a smaller file (<50 MB). 3) Retry.`))
        }

        xhr.onabort = () => {
          reject(new Error('Upload was cancelled'))
        }

        // Construct the full URL
        const uploadUrl = API_URL === '' 
          ? '/api/v1/analysis/upload'  // Relative URL
          : `${API_URL}/api/v1/analysis/upload`  // Absolute URL
        
        console.log('Opening XHR connection to:', uploadUrl)
        console.log('API_URL:', API_URL, '(empty = relative, non-empty = absolute)')
        console.log('Window origin:', window.location.origin)
        console.log('Full URL will be:', API_URL === '' ? `${window.location.origin}${uploadUrl}` : uploadUrl)
        
        xhr.open('POST', uploadUrl)
        xhr.timeout = 600000 // 10 minutes
        xhrRef.current = xhr
        xhr.send(formData)
      })

      const id = await uploadPromise
      console.log('Upload complete. Analysis ID:', id)
      setAnalysisId(id)
      progressRef.current = 100 // Update ref
      setProgress(100)
      
      // Immediately transition to processing state with initial step
      setStatus('processing')
      setCurrentStep('pose_estimation')
      setStepProgress(0)
      setStepMessage('Upload complete. Initializing analysis...')
      
      // Store analysis ID in localStorage for resume capability
      localStorage.setItem('lastAnalysisId', id)

      // Start polling immediately - backend should have analysis ready
      // Reduced delay from 2000ms to 500ms for faster response
      // Backend verification ensures analysis is readable before returning
      await new Promise(resolve => setTimeout(resolve, 500))

      pollAnalysisStatus(id)
    } catch (err: any) {
      console.error('Upload error:', err)
      
      // CRITICAL: Clear ALL state when upload fails to prevent misleading UI
      setStatus('failed')
      setAnalysisId(null)
      setCurrentStep(null)
      setStepProgress(0)
      setStepMessage('')
      progressRef.current = 0
      setProgress(0)
      
      // Clear any stored analysis ID
      localStorage.removeItem('lastAnalysisId')
      
      // Clear polling timeout if any
      clearPollTimeout()
      
      // Abort XHR if still active
      if (xhrRef.current) {
        xhrRef.current.abort()
        xhrRef.current = null
      }
      
      // Provide better error messages for specific error codes
      let errorMessage = err.message || 'Upload failed. Please try again.'
      
      // Handle 502 Bad Gateway specifically
      if (errorMessage.includes('502') || errorMessage.includes('Bad Gateway')) {
        errorMessage = `Upload failed: Server Error (502 Bad Gateway)\n\n` +
          `The backend server is temporarily unavailable. This usually means:\n\n` +
          `• The server is restarting or deploying\n` +
          `• The server is overloaded\n` +
          `• There's a network/proxy issue\n\n` +
          `Please try:\n` +
          `1. Wait 30-60 seconds and try again\n` +
          `2. Check if the server is running\n` +
          `3. Try with a smaller file if the issue persists\n\n` +
          `If the problem continues, the server may need to be restarted.`
      } else if (errorMessage.includes('500')) {
        errorMessage = `Upload failed: Internal Server Error (500)\n\n` +
          `The server encountered an error processing your upload.\n\n` +
          `Please try:\n` +
          `1. Wait a moment and try again\n` +
          `2. Try with a smaller file (<50 MB)\n` +
          `3. Check the file format (MP4, AVI, MOV, MKV)\n\n` +
          `If the problem persists, contact support.`
      } else if (errorMessage.includes('503')) {
        errorMessage = `Upload failed: Service Unavailable (503)\n\n` +
          `The service is temporarily unavailable.\n\n` +
          `Please wait a few moments and try again.`
      } else if (errorMessage.includes('timeout') || errorMessage.includes('Timeout')) {
        errorMessage = `Upload failed: Request Timeout\n\n` +
          `The upload took too long to complete.\n\n` +
          `Please try:\n` +
          `1. Use a smaller file (<50 MB)\n` +
          `2. Check your internet connection\n` +
          `3. Try again`
      } else if (errorMessage.includes('network') || errorMessage.includes('Network')) {
        errorMessage = `Upload failed: Network Error\n\n` +
          `Unable to connect to the server.\n\n` +
          `Please check:\n` +
          `1. Your internet connection\n` +
          `2. If the server is running\n` +
          `3. Try again in a moment`
      }
      
      setError(errorMessage)
    }
  }

  const pollAnalysisStatus = async (id: string) => {
    let consecutiveErrors = 0
    let consecutive404s = 0
    const maxConsecutiveErrors = 5
    const maxConsecutive404s = 6
    const startTime = Date.now()
    const initialGracePeriod = 15000 // 15s – backend may take time to persist analysis
    
    await new Promise(resolve => setTimeout(resolve, 3000)) // 3s initial delay
    
    const schedulePoll = (delayMs: number) => {
      clearPollTimeout()
      pollTimeoutRef.current = window.setTimeout(poll, delayMs)
    }
    
    const poll = async () => {
      try {
        const pollUrl = `${API_URL}/api/v1/analysis/${id}`
        const response = await fetch(pollUrl)
        
        if (response.status === 404) {
          const timeSinceStart = Date.now() - startTime
          if (timeSinceStart < initialGracePeriod) {
            consecutive404s++
            if (consecutive404s >= maxConsecutive404s) {
              setStatus('failed')
              setError(`Analysis not found after ${maxConsecutive404s} attempts. The server may still be creating it. Try again in a moment or re-upload.`)
              setAnalysisId(null)
              return
            }
            const retryDelay = 600 * consecutive404s
            schedulePoll(retryDelay)
            return
          }
          setStatus('failed')
          setError(`Analysis not found (${(timeSinceStart / 1000).toFixed(0)}s after upload). It may have been lost. Please try uploading again.`)
          setAnalysisId(null)
          return
        }
        
        consecutive404s = 0
        
        if (!response.ok) {
          consecutiveErrors++
          if (consecutiveErrors >= maxConsecutiveErrors) {
            throw new Error(`Failed to fetch analysis status after ${maxConsecutiveErrors} attempts: ${response.statusText}`)
          }
          schedulePoll(3000 * consecutiveErrors)
          return
        }

        // Reset error counter on success
        consecutiveErrors = 0
        
        const data = await response.json()
        const analysisStatus = data.status

        // Update video quality info if available
        if (data.video_quality_score !== undefined || data.video_quality_issues) {
          setVideoQuality({
            score: data.video_quality_score ?? null,
            isValid: data.video_quality_valid ?? null,
            issues: data.video_quality_issues || [],
            recommendations: data.video_quality_recommendations || [],
            poseDetectionRate: data.pose_detection_rate ?? null
          })
        }
        
        // Use real progress data from backend
        if (analysisStatus === 'completed') {
          // Backend has marked analysis as completed - this is the natural completion
          // Trust the backend's status and display completion
          setStatus('completed')
          setCurrentStep('report_generation')
          setStepProgress(100)
          setStepMessage(data.step_message || 'Analysis complete! Report ready.')
          clearPollTimeout()
          console.log('✅ Analysis completed naturally - backend set status to completed')
        } else if (analysisStatus === 'processing') {
          // CRITICAL: Handle case where stepProgress=100 but status is still 'processing'
          // This happens when backend says "complete" but database update hasn't finished
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
          
          // CRITICAL: Do NOT force completion - wait for backend to set status='completed'
          // Step 4 should complete naturally when backend finishes saving to database
          // Only update UI state, don't force status change
          // The backend will set status='completed' when Step 4 is truly done
          
          console.log(`Progress update: ${backendStep} - ${backendProgress}% - ${backendMessage}`)
          
          // For Step 4, poll more frequently to show detailed progress
          if (mappedStep === 'report_generation') {
            if (backendProgress >= 98) {
              schedulePoll(500) // Poll every 500ms when finalizing (98-100%)
            } else {
              schedulePoll(1000) // Poll every 1s during Step 4 (95-98%)
            }
          } else {
            schedulePoll(2000)
          }
        } else if (analysisStatus === 'failed') {
          setStatus('failed')
          
          // Build detailed error message with step information
          const failedStep = data.current_step || 'unknown'
          const stepNames: Record<string, string> = {
            'pose_estimation': 'Step 1: Pose Estimation',
            '3d_lifting': 'Step 2: 3D Lifting',
            'metrics_calculation': 'Step 3: Metrics Calculation',
            'report_generation': 'Step 4: Report Generation'
          }
          const stepName = stepNames[failedStep] || `Step: ${failedStep}`
          
          const errorMsg = data.step_message || data.error || 'Analysis failed'
          const detailedError = `❌ Analysis Failed at ${stepName}\n\n${errorMsg}\n\nPlease try:\n• Uploading the video again\n• Using a smaller file (<50 MB)\n• Ensuring good lighting and clear visibility of the person\n• Recording 5-10 seconds of continuous walking`
          
          setError(detailedError)
          setCurrentStep(failedStep as ProcessingStep || 'pose_estimation')
          setStepProgress(data.step_progress || 0)
          setStepMessage(data.step_message || 'Analysis failed')
        }
      } catch (err: any) {
        console.error('Polling error:', err)
        consecutiveErrors++
        if (consecutiveErrors >= maxConsecutiveErrors) {
          setStatus('failed')
          setError(`Failed to get analysis status after ${maxConsecutiveErrors} attempts. ${err.message || 'Please try uploading again.'}`)
          setAnalysisId(null)
          return
        }
        schedulePoll(3000 * consecutiveErrors)
      }
    }

    // Start polling
    poll()
  }

  const handleCancel = async () => {
    // Cancel upload if in progress
    if (xhrRef.current && (status === 'uploading' || status === 'processing')) {
      xhrRef.current.abort()
      xhrRef.current = null
    }
    clearPollTimeout()
    
    // Cancel backend processing if analysis is running
    if (analysisId && (status === 'processing' || status === 'uploading')) {
      try {
        const response = await fetch(`${API_URL}/api/v1/analysis/${analysisId}/cancel`, {
          method: 'POST',
          headers: {
            'Accept': 'application/json',
          },
        })
        
        if (response.ok) {
          console.log('✅ Analysis cancelled on backend')
        } else {
          console.warn('⚠️ Failed to cancel analysis on backend, but continuing with local cancellation')
        }
      } catch (error) {
        console.warn('⚠️ Error calling cancel endpoint:', error)
        // Continue with local cancellation even if backend call fails
      }
    }
    
    // Clear localStorage
    if (analysisId) {
      localStorage.removeItem('lastAnalysisId')
    }
    
    // CRITICAL: Fully reset state to ready for new upload
    // Don't navigate away - just reset to idle state so user can select new file
    setStatus('idle')
    setProgress(0)
    setCurrentStep(null)
    setStepProgress(0)
    setStepMessage('')
    setAnalysisId(null)
    setFile(null)
    setError(null)
    progressRef.current = 0
    
    // Clear file input if it exists
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    if (fileInput) {
      fileInput.value = ''
    }
    
    console.log('✅ Cancellation complete - ready for new file upload')
  }

  // CRITICAL: On mount, cancel and clean up any previous processing
  // When user navigates to this URL, assume it's a new request and start fresh
  useEffect(() => {
    const cleanupPreviousProcessing = async () => {
      console.log('🔄 Page loaded - cleaning up any previous processing for fresh start')
      
      // Stop any ongoing uploads/polls immediately
      if (xhrRef.current) {
        xhrRef.current.abort()
        xhrRef.current = null
      }
      clearPollTimeout()
      
      // Get any processing analysis from localStorage
      const lastAnalysisId = localStorage.getItem('lastAnalysisId')
      
      // Cancel backend processing if there's an active analysis
      if (lastAnalysisId) {
        try {
          // Check if it's still processing
          const checkResponse = await fetch(`${API_URL}/api/v1/analysis/${lastAnalysisId}`)
          if (checkResponse.ok) {
            const data = await checkResponse.json()
            if (data.status === 'processing' || data.status === 'uploading') {
              // Cancel it on the backend
              console.log(`🛑 Cancelling previous processing analysis: ${lastAnalysisId}`)
              try {
                const cancelResponse = await fetch(`${API_URL}/api/v1/analysis/${lastAnalysisId}/cancel`, {
                  method: 'POST',
                  headers: {
                    'Accept': 'application/json',
                  },
                })
                if (cancelResponse.ok) {
                  console.log('✅ Previous analysis cancelled on backend')
                } else {
                  console.warn('⚠️ Failed to cancel previous analysis on backend, but continuing with cleanup')
                }
              } catch (cancelErr) {
                console.warn('⚠️ Error calling cancel endpoint:', cancelErr)
                // Continue with cleanup even if cancel fails
              }
            }
          }
        } catch (err) {
          console.warn('⚠️ Error checking previous analysis:', err)
          // Continue with cleanup
        }
      }
      
      // Clear all state - start fresh
      setStatus('idle')
      setProgress(0)
      setCurrentStep(null)
      setStepProgress(0)
      setStepMessage('')
      setAnalysisId(null)
      setFile(null)
      setError(null)
      setVideoQuality(null)
      setProcessingFrameRate(null)
      setVideoFPS(null)
      progressRef.current = 0
      
      // Clear localStorage
      localStorage.removeItem('lastAnalysisId')
      
      // Clear file input if it exists
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
      if (fileInput) {
        fileInput.value = ''
      }
      
      console.log('✅ Cleanup complete - ready for new file upload')
    }

    cleanupPreviousProcessing()
  }, [])

  useEffect(() => {
    return () => {
      if (xhrRef.current) xhrRef.current.abort()
      clearPollTimeout()
    }
  }, [])

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

        {/* Processing Frame Rate Selection */}
        {file && status === 'idle' && (
          <div className="processing-options" style={{
            marginTop: '1.5rem',
            padding: '1.5rem',
            backgroundColor: '#f8f9fa',
            borderRadius: '8px',
            border: '1px solid #e9ecef'
          }}>
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.1rem', color: '#2c3e50' }}>
              ⚡ Processing Speed Options
            </h3>
            <p style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', color: '#666' }}>
              <strong>Note:</strong> Video frame rate will be auto-detected. Choose processing rate below (lower = faster, higher = more accurate).
            </p>
            <p style={{ margin: '0 0 1rem 0', fontSize: '0.9rem', color: '#666' }}>
              Choose how many frames per second to process. Lower rates = faster analysis, higher rates = more accurate results.
            </p>
            <div className="frame-rate-options" style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
              gap: '0.75rem'
            }}>
              {[
                { value: 10, label: '10 fps', desc: 'Fastest', time: '~2-3 min' },
                { value: 15, label: '15 fps', desc: 'Balanced', time: '~3-5 min' },
                { value: 20, label: '20 fps', desc: 'Accurate', time: '~4-7 min' },
                { value: 30, label: '30 fps', desc: 'Most Accurate', time: '~6-10 min' }
              ].map((option) => {
                // Highlight if it matches video FPS (or closest to it)
                const isVideoFPS = videoFPS && Math.abs(videoFPS - option.value) < 5
                const isDefault = processingFrameRate === option.value
                
                return (
                  <label
                    key={option.value}
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      padding: '1rem',
                      border: isDefault ? '2px solid #3498db' : isVideoFPS ? '2px solid #2ecc71' : '1px solid #ddd',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      backgroundColor: isDefault ? '#e8f4f8' : isVideoFPS ? '#f0f9f4' : 'white',
                      transition: 'all 0.2s',
                      position: 'relative'
                    }}
                  >
                    <input
                      type="radio"
                      name="processingFrameRate"
                      value={option.value}
                      checked={processingFrameRate === option.value}
                      onChange={(e) => setProcessingFrameRate(Number(e.target.value))}
                      style={{ marginBottom: '0.5rem' }}
                    />
                    <strong style={{ fontSize: '1rem', color: '#2c3e50' }}>{option.label}</strong>
                    {isVideoFPS && !isDefault && (
                      <span style={{ fontSize: '0.7rem', color: '#2ecc71', fontWeight: '600', marginTop: '0.25rem' }}>
                        (Video FPS)
                      </span>
                    )}
                    {isDefault && (
                      <span style={{ fontSize: '0.7rem', color: '#3498db', fontWeight: '600', marginTop: '0.25rem' }}>
                        (Selected)
                      </span>
                    )}
                    <span style={{ fontSize: '0.85rem', color: '#666', marginTop: '0.25rem' }}>{option.desc}</span>
                    <span style={{ fontSize: '0.75rem', color: '#999', marginTop: '0.25rem' }}>{option.time}</span>
                  </label>
                )
              })}
            </div>
            <p style={{ margin: '1rem 0 0 0', fontSize: '0.85rem', color: '#666', fontStyle: 'italic' }}>
              💡 Tip: Processing at 20-30 fps gives best accuracy. Lower rates (10-15 fps) are faster but may reduce precision. The system will use the video's actual frame rate for calculations.
            </p>
          </div>
        )}

        {/* Show error message prominently when upload fails */}
        {error && status === 'failed' && (
          <div className="error" style={{ 
            marginTop: '1rem', 
            padding: '1rem', 
            backgroundColor: '#fee', 
            border: '2px solid #f00', 
            borderRadius: '8px',
            maxWidth: '100%'
          }}>
            <div style={{ fontWeight: 'bold', marginBottom: '0.5rem', fontSize: '1.1em' }}>
              ❌ Upload Failed
            </div>
            {error.split('\n').map((line, idx) => (
              <div key={idx} style={{ marginBottom: '0.25rem' }}>{line}</div>
            ))}
            <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid #fcc' }}>
              <button 
                onClick={() => {
                  // Reset all state for retry
                  setError(null)
                  setStatus('idle')
                  setFile(null)
                  setAnalysisId(null)
                  setCurrentStep(null)
                  setStepProgress(0)
                  setStepMessage('')
                  setProgress(0)
                  progressRef.current = 0
                  localStorage.removeItem('lastAnalysisId')
                  clearPollTimeout()
                  if (xhrRef.current) {
                    xhrRef.current.abort()
                    xhrRef.current = null
                  }
                }}
                className="btn btn-primary"
                style={{ marginRight: '0.5rem' }}
              >
                Try Again
              </button>
              <button 
                onClick={() => {
                  setFile(null)
                  setError(null)
                  setStatus('idle')
                  setAnalysisId(null)
                  setCurrentStep(null)
                  setStepProgress(0)
                  setStepMessage('')
                  setProgress(0)
                  progressRef.current = 0
                }}
                className="btn btn-secondary"
              >
                Select Different File
              </button>
            </div>
          </div>
        )}
        
        {/* Show error for other states (idle) */}
        {error && status === 'idle' && (
          <div className="error">
            {error.split('\n').map((line, idx) => (
              <div key={idx}>{line}</div>
            ))}
          </div>
        )}
        
        {/* Video Quality Information */}
        {videoQuality && (status === 'processing' || status === 'completed') && (
          <div className={`video-quality-info ${videoQuality.isValid === false ? 'quality-warning' : videoQuality.score && videoQuality.score >= 80 ? 'quality-good' : 'quality-moderate'}`}>
            <div className="quality-header">
              <strong>📹 Video Quality Assessment</strong>
              {videoQuality.score !== null && (
                <span className="quality-score">
                  Score: {videoQuality.score.toFixed(0)}%
                  {videoQuality.isValid === false && ' ⚠️'}
                  {videoQuality.isValid === true && videoQuality.score >= 80 && ' ✅'}
                </span>
              )}
            </div>
            
            {videoQuality.poseDetectionRate !== null && (
              <div className="quality-metric">
                <span>Pose Detection Rate: {(videoQuality.poseDetectionRate * 100).toFixed(0)}%</span>
              </div>
            )}
            
            {videoQuality.issues && videoQuality.issues.length > 0 && (
              <div className="quality-issues">
                <strong>Issues Detected:</strong>
                <ul>
                  {videoQuality.issues.slice(0, 3).map((issue, idx) => (
                    <li key={idx}>{issue}</li>
                  ))}
                </ul>
              </div>
            )}
            
            {videoQuality.recommendations && videoQuality.recommendations.length > 0 && videoQuality.isValid === false && (
              <div className="quality-recommendations">
                <strong>💡 Recommendations for Better Results:</strong>
                <ul>
                  {videoQuality.recommendations.slice(0, 5).map((rec, idx) => (
                    <li key={idx}>{rec}</li>
                  ))}
                </ul>
                <div className="quality-note">
                  <strong>For Geriatric Functional Mobility Assessment:</strong>
                  <ul>
                    <li>Record 5-10 seconds of continuous walking</li>
                    <li>Use side view for best gait parameter visibility</li>
                    <li>Ensure person walks at comfortable pace</li>
                    <li>Include at least 3-4 complete gait cycles</li>
                    <li>Record on flat, level surface</li>
                    <li>Good lighting with person clearly visible</li>
                  </ul>
                </div>
              </div>
            )}
          </div>
        )}
        
        {status === 'processing' && currentStep === 'report_generation' && (
          <div className="info-message" style={{ 
            marginTop: '1rem', 
            padding: '1rem', 
            backgroundColor: '#f0f8ff', 
            border: '1px solid #4a90e2', 
            borderRadius: '8px' 
          }}>
            <p style={{ margin: 0, fontWeight: '500' }}>
              {stepProgress < 95 && '🔄 Step 4: Starting report generation...'}
              {stepProgress >= 95 && stepProgress < 98 && '📊 Step 4: Validating metrics and preparing report...'}
              {stepProgress >= 98 && stepProgress < 100 && (
                stepMessage.includes('Retrying') 
                  ? `🔄 ${stepMessage}` 
                  : '💾 Step 4: Saving analysis results to database... This will take just a moment.'
              )}
              {stepProgress === 100 && '✅ Step 4: Report generation complete!'}
            </p>
            {stepProgress >= 98 && stepProgress < 100 && (
              <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.9em', color: '#666' }}>
                {stepMessage || 'Finalizing analysis and saving results to database...'}
              </p>
            )}
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

        {/* Show processing steps when processing OR when processing failed (but not when upload failed) */}
        {/* Upload failures don't have currentStep set, so we check for that */}
        {(status === 'processing' || (status === 'failed' && currentStep !== null)) && (
          <div className="processing-details apple-style">
            <div className="processing-header">
              <div className="processing-title-row">
                <div>
                  <h3>Analyzing Your Video</h3>
                  <p className="processing-subtitle">This may take a few minutes. We'll keep you updated.</p>
                </div>
                <button
                  onClick={handleCancel}
                  className="btn-cancel"
                  title="Cancel analysis"
                >
                  <X size={18} />
                  Cancel
                </button>
              </div>
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
                  <span className="overall-progress-percent">
                    {stepProgress}%
                  </span>
                </div>
                <div className="overall-progress-bar-container">
                  <div 
                    className="overall-progress-bar" 
                    style={{ 
                      width: `${stepProgress}%` 
                    }}
                  ></div>
                </div>
                <p className="overall-progress-message">
                  {stepMessage || `Processing ${currentStep.replace('_', ' ')}...`}
                </p>
                <div className="progress-time-info">
                  <span className="time-elapsed">
                    Elapsed: {Math.floor((Date.now() - startTime) / 1000)}s
                  </span>
                  {status === 'processing' && stepProgress > 0 && stepProgress < 100 && (
                    <span className="time-remaining">
                      Est. remaining: {Math.floor(((Date.now() - startTime) / stepProgress) * (100 - stepProgress) / 1000)}s
                    </span>
                  )}
                </div>
              </div>
            )}

            <div className="processing-steps apple-steps">
              <div className={`step-card ${currentStep === 'pose_estimation' ? (status === 'failed' ? 'failed' : 'active') : currentStep && ['3d_lifting', 'metrics_calculation', 'report_generation'].includes(currentStep) ? 'completed' : 'pending'}`}>
                <div className="step-indicator">
                  {currentStep === 'pose_estimation' && status === 'failed' ? (
                    <div className="step-error">✗</div>
                  ) : currentStep && ['3d_lifting', 'metrics_calculation', 'report_generation'].includes(currentStep) ? (
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
                  <div className="step-title">
                    <span className="step-number-label">Step 1:</span> Pose Estimation
                  </div>
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
              
              <div className={`step-card ${currentStep === '3d_lifting' ? (status === 'failed' ? 'failed' : 'active') : currentStep && ['metrics_calculation', 'report_generation'].includes(currentStep) ? 'completed' : 'pending'}`}>
                <div className="step-indicator">
                  {currentStep === '3d_lifting' && status === 'failed' ? (
                    <div className="step-error">✗</div>
                  ) : currentStep && ['metrics_calculation', 'report_generation'].includes(currentStep) ? (
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
                  <div className="step-title">
                    <span className="step-number-label">Step 2:</span> 3D Lifting
                  </div>
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
              
              <div className={`step-card ${currentStep === 'metrics_calculation' ? (status === 'failed' ? 'failed' : 'active') : currentStep === 'report_generation' ? 'completed' : 'pending'}`}>
                <div className="step-indicator">
                  {currentStep === 'metrics_calculation' && status === 'failed' ? (
                    <div className="step-error">✗</div>
                  ) : currentStep === 'report_generation' ? (
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
                  <div className="step-title">
                    <span className="step-number-label">Step 3:</span> Metrics Calculation
                  </div>
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
              
              <div className={`step-card ${
                currentStep === 'report_generation'
                  ? status === 'failed'
                    ? 'failed'
                    : (status as UploadStatus) === 'completed'
                      ? 'completed'
                      : 'active'
                  : (status as UploadStatus) === 'completed'
                    ? 'completed'
                    : 'pending'
              }`}>
                <div className="step-indicator">
                  {status === 'failed' && currentStep === 'report_generation' ? (
                    <div className="step-error">✗</div>
                  ) : (status as UploadStatus) === 'completed' ? (
                    <div className="step-checkmark">✓</div>
                  ) : currentStep === 'report_generation' ? (
                    <div className="step-spinner">
                      <Loader2 className="spinner-icon" />
                    </div>
                  ) : (
                    <div className="step-number">4</div>
                  )}
                </div>
                <div className="step-content">
                  <div className="step-title">
                    <span className="step-number-label">Step 4:</span> Report Generation
                  </div>
                  <div className="step-description">
                    {(status as UploadStatus) === 'completed' 
                      ? 'Analysis complete! Report ready.'
                      : currentStep === 'report_generation' 
                      ? (stepMessage || 'Generating detailed analysis reports...')
                      : currentStep && ['pose_estimation', '3d_lifting', 'metrics_calculation'].includes(currentStep)
                      ? 'Waiting for previous steps...'
                      : 'Generating analysis reports'}
                  </div>
                  {currentStep === 'report_generation' && status === 'processing' && stepProgress > 0 && stepProgress < 100 && (
                    <div className="step-progress-indicator">
                      <div className="step-progress-track">
                        <div className="step-progress-fill" style={{ width: `${stepProgress}%` }}></div>
                      </div>
                      <span className="step-progress-text">{stepProgress}%</span>
                    </div>
                  )}
                </div>
              </div>
              
              {/* View Report Button - Show below Step 4 when completed */}
              {(status as UploadStatus) === 'completed' && analysisId && (
                <div className="step-4-actions" style={{ 
                  marginTop: '1.5rem', 
                  padding: '1.5rem',
                  backgroundColor: '#f8f9fa',
                  borderRadius: '8px',
                  border: '1px solid #e9ecef'
                }}>
                  <div style={{ textAlign: 'center', marginBottom: '1rem' }}>
                    <h4 style={{ margin: '0 0 0.5rem 0', color: '#2c3e50' }}>✅ Analysis Complete!</h4>
                    <p style={{ margin: 0, color: '#666', fontSize: '0.95rem' }}>
                      Your gait analysis report is ready to view.
                    </p>
                  </div>
                  <div style={{ display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
                    <button 
                      onClick={() => {
                        // Simple navigation - if status is completed, go to report
                        // The report page will handle loading and validation
                        navigate(`/report/${analysisId}`)
                      }}
                      className="btn btn-primary btn-large"
                      style={{ minWidth: '200px', fontSize: '1.1rem', padding: '1rem 2rem' }}
                    >
                      View Report
                    </button>
                  </div>
                </div>
              )}
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
