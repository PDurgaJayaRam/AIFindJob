import React, { useState, useEffect } from 'react'
import axios from 'axios'
import { 
  Zap, 
  Play, 
  Pause, 
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
  Loader2
} from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function Pipeline() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState([])

  useEffect(() => {
    loadStatus()
  }, [])

  const loadStatus = async () => {
    try {
      const response = await axios.get(`${API}/scheduler/status`)
      setStatus(response.data)
    } catch (error) {
      console.error('Error loading status:', error)
    } finally {
      setLoading(false)
    }
  }

  const triggerPipeline = async () => {
    setRunning(true)
    try {
      await axios.post(`${API}/scheduler/trigger`)
      setLogs(prev => [...prev, { 
        time: new Date().toLocaleTimeString(), 
        message: 'Pipeline triggered successfully!',
        type: 'success'
      }])
      alert('Pipeline triggered! It will run in the background.')
    } catch (error) {
      setLogs(prev => [...prev, { 
        time: new Date().toLocaleTimeString(), 
        message: 'Error: ' + (error.response?.data?.detail || error.message),
        type: 'error'
      }])
    } finally {
      setRunning(false)
    }
  }

  const pipelineStages = [
    { name: 'Job Discovery', description: 'Scraping 13+ portals', icon: '🔍', status: 'active' },
    { name: 'Job Intelligence', description: 'AI analysis & scoring', icon: '🧠', status: 'active' },
    { name: 'Resume Matching', description: 'ATS compatibility check', icon: '📄', status: 'active' },
    { name: 'Company Research', description: 'Deep company analysis', icon: '🏢', status: 'active' },
    { name: 'People Finding', description: 'Discover employees', icon: '👥', status: 'active' },
    { name: 'Smart Outreach', description: 'Personalized messages', icon: '✉️', status: 'active' },
    { name: 'Auto-Apply', description: 'Submit applications', icon: '🚀', status: 'active' },
  ]

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <Loader2 className="animate-spin h-12 w-12 text-blue-500 mx-auto mb-4" />
          <p className="text-gray-500">Loading pipeline status...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Pipeline Control</h1>
          <p className="text-gray-500 mt-1">Monitor and control the AI job search pipeline</p>
        </div>
        <button
          onClick={triggerPipeline}
          disabled={running}
          className="bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50 flex items-center gap-2"
        >
          {running ? (
            <Loader2 size={20} className="animate-spin" />
          ) : (
            <Play size={20} />
          )}
          Run Pipeline Now
        </button>
      </div>

      {/* Status Card */}
      <div className="bg-gradient-to-r from-green-500 to-blue-500 rounded-xl p-6 text-white">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold mb-2">Pipeline Status</h2>
            <p className="text-green-100">
              {status?.status === 'active' 
                ? `✅ Active - Running every ${status.interval_minutes || 30} minutes`
                : '⚠️ Pipeline not active'}
            </p>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold">13+</div>
            <div className="text-green-100">portals connected</div>
          </div>
        </div>
      </div>

      {/* Pipeline Stages */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h2 className="text-lg font-semibold mb-6">Pipeline Stages</h2>
        <div className="space-y-4">
          {pipelineStages.map((stage, idx) => (
            <div key={stage.name} className="flex items-center gap-4 p-4 bg-gray-50 rounded-lg">
              <div className="text-2xl">{stage.icon}</div>
              <div className="flex-1">
                <div className="font-medium text-gray-900">{stage.name}</div>
                <div className="text-sm text-gray-500">{stage.description}</div>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle size={20} className="text-green-500" />
                <span className="text-sm font-medium text-green-600">Active</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Activity Logs */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h2 className="text-lg font-semibold mb-4">Activity Logs</h2>
        {logs.length > 0 ? (
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {logs.map((log, idx) => (
              <div 
                key={idx} 
                className={`p-3 rounded-lg text-sm ${
                  log.type === 'success' ? 'bg-green-50 text-green-800' :
                  log.type === 'error' ? 'bg-red-50 text-red-800' :
                  'bg-gray-50 text-gray-800'
                }`}
              >
                <span className="font-mono text-xs mr-2">[{log.time}]</span>
                {log.message}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-gray-400">
            <Clock size={48} className="mx-auto mb-4 opacity-50" />
            <p>No activity yet. Run the pipeline to see logs.</p>
          </div>
        )}
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <div className="text-3xl font-bold text-blue-600">13+</div>
          <div className="text-gray-500">Job Portals</div>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <div className="text-3xl font-bold text-green-600">30 min</div>
          <div className="text-gray-500">Refresh Interval</div>
        </div>
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <div className="text-3xl font-bold text-purple-600">24/7</div>
          <div className="text-gray-500">Always Running</div>
        </div>
      </div>
    </div>
  )
}
