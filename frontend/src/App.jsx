import React from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './components/Dashboard'
import JobSearch from './components/JobSearch'
import Companies from './components/Companies'
import People from './components/People'
import Outreach from './components/Outreach'
import Pipeline from './components/Pipeline'
import Settings from './components/Settings'
import LiveScraper from './components/LiveScraper'

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/jobs" element={<JobSearch />} />
          <Route path="/companies" element={<Companies />} />
          <Route path="/people" element={<People />} />
          <Route path="/outreach" element={<Outreach />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/live" element={<LiveScraper />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}

export default App
