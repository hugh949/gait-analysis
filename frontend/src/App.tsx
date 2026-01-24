import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import AnalysisUpload from './pages/AnalysisUpload'
import ViewReports from './pages/ViewReports'
import Report from './pages/Report'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={
          <Layout>
            <AnalysisUpload />
          </Layout>
        } />
        <Route path="/reports" element={
          <Layout>
            <ViewReports />
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
