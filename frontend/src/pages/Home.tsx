import { Link } from 'react-router-dom'
import './Home.css'

export default function Home() {
  return (
    <div className="home">
      <div className="hero">
        <h1>Gait Analysis Platform</h1>
        <p className="subtitle">
          Transform basic RGB video into clinical-grade biomechanical metrics
          for fall risk assessment and mobility monitoring
        </p>
        <Link to="/upload" className="btn btn-primary">
          Start Analysis
        </Link>
      </div>

      <div className="features">
        <div className="feature-card">
          <h3>For Medical Professionals</h3>
          <p>
            Comprehensive biomechanical tabulations, confidence metrics, and 
            EMR integration with HL7/FHIR formats
          </p>
          <Link to="/medical" className="btn btn-secondary">
            View Medical Dashboard
          </Link>
        </div>

        <div className="feature-card">
          <h3>For Family Caregivers</h3>
          <p>
            Simple monitoring dashboard with fall risk indicators and trend 
            tracking to prompt proactive clinical consultation
          </p>
          <Link to="/caregiver" className="btn btn-secondary">
            View Caregiver Dashboard
          </Link>
        </div>

        <div className="feature-card">
          <h3>For Older Adults</h3>
          <p>
            Intuitive summary with gait health score and visual feedback to 
            build trust and demonstrate focus on movement
          </p>
          <Link to="/older-adult" className="btn btn-secondary">
            View Your Dashboard
          </Link>
        </div>
      </div>

      <div className="info-section">
        <h2>Key Features</h2>
        <ul>
          <li>Gold standard equivalence validated against IR-marker systems</li>
          <li>Clinical priority metrics: Gait speed, stride variability, clearance</li>
          <li>Multi-view fusion for comprehensive analysis</li>
          <li>Environmental robustness for home environments</li>
          <li>Quality gating ensures reliable results</li>
        </ul>
      </div>
    </div>
  )
}



