import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import AnalysisUpload from './pages/AnalysisUpload'
import ViewGait from './pages/ViewGait'
import Report from './pages/Report'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/upload" replace />} />
        <Route path="/upload" element={
          <Layout>
            <AnalysisUpload />
          </Layout>
        } />
        <Route path="/view-gait" element={
          <Layout>
            <ViewGait />
          </Layout>
        } />
        <Route path="/report/:analysisId" element={
          <Layout>
            <Report />
          </Layout>
        } />
      </Routes>
    </BrowserRouter>
  )
}

export default App
