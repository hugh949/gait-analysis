import { useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import AnalysisUpload from './pages/AnalysisUpload'
import MedicalDashboard from './pages/MedicalDashboard'
import CaregiverDashboard from './pages/CaregiverDashboard'
import OlderAdultDashboard from './pages/OlderAdultDashboard'

function App() {
  const [selectedAudience, setSelectedAudience] = useState('home')

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={
          <Layout selectedAudience={selectedAudience} setSelectedAudience={setSelectedAudience}>
            <Home />
          </Layout>
        } />
        <Route path="/upload" element={
          <Layout selectedAudience={selectedAudience} setSelectedAudience={setSelectedAudience}>
            <AnalysisUpload />
          </Layout>
        } />
        <Route path="/medical" element={
          <Layout selectedAudience={selectedAudience} setSelectedAudience={setSelectedAudience}>
            <MedicalDashboard />
          </Layout>
        } />
        <Route path="/caregiver" element={
          <Layout selectedAudience={selectedAudience} setSelectedAudience={setSelectedAudience}>
            <CaregiverDashboard />
          </Layout>
        } />
        <Route path="/older-adult" element={
          <Layout selectedAudience={selectedAudience} setSelectedAudience={setSelectedAudience}>
            <OlderAdultDashboard />
          </Layout>
        } />
      </Routes>
    </BrowserRouter>
  )
}

export default App
