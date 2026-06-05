import React, { useState, useEffect, useRef } from 'react'
import axios from 'axios'
import { 
  Eye, 
  Play, 
  Square, 
  RefreshCw, 
  Globe,
  Activity,
  CheckCircle,
  AlertCircle,
  Loader2,
  Camera,
  Building2
} from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function LiveScraper() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [refreshInterval, setRefreshInterval] = useState(2) // seconds
  const intervalRef = useRef(null)

  useEffect(() => {
    loadStatus()
  }, [])

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(loadStatus, refreshInterval * 1000)
    } else {
      clearInterval(intervalRef.current)
    }
    return () => clearInterval(intervalRef.current)
  }, [autoRefresh, refreshInterval])

  const loadStatus = async () => {
    try {
      const response = await axios.get(`${API}/live-scraper/status`)
      setStatus(response.data)
    } catch (error) {
      console.error('Error loading status:', error)
    } finally {
      setLoading(false)
    }
  }

  const startScraper = async () => {
    try {
      await axios.post(`${API}/live-scraper/start`)
      await axios.post(`${API}/scheduler/trigger`)
      setTimeout(loadStatus, 1000)
    } catch (error) {
      alert('Error: ' + (error.response?.data?.detail || error.message))
    }
  }

  const runDemo = async () => {
    try {
      await axios.post(`${API}/live-scraper/demo`)
      setTimeout(loadStatus, 1000)
    } catch (error) {
      alert('Error: ' + (error.response?.data?.detail || error.message))
    }
  }

  const stopScraper = async () => {
    try {
      await axios.post(`${API}/live-scraper/stop`)
      loadStatus()
    } catch (error) {
      console.error('Error stopping:', error)
    }
  }

  const formatTime = (isoString) => {
    if (!isoString) return '—'
    return new Date(isoString).toLocaleTimeString()
  }

  const formatElapsed = (seconds) => {
    if (!seconds) return '0s'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}m ${secs}s`
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="animate-spin h-12 w-12 text-blue-500" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 flex items-center gap-3">
            <Eye size={32} className="text-blue-600" />
            Live Scraper Viewer
          </h1>
          <p className="text-gray-500 mt-1">Watch the browser scrape jobs in real-time</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={runDemo}
            className="bg-blue-600 text-white px-5 py-3 rounded-lg font-medium hover:bg-blue-700 transition flex items-center gap-2"
          >
            <Play size={20} />
            Run Demo
          </button>
          {status?.is_running ? (
            <button
              onClick={stopScraper}
              className="bg-red-600 text-white px-5 py-3 rounded-lg font-medium hover:bg-red-700 transition flex items-center gap-2"
            >
              <Square size={20} />
              Stop
            </button>
          ) : (
            <button
              onClick={startScraper}
              className="bg-green-600 text-white px-5 py-3 rounded-lg font-medium hover:bg-green-700 transition flex items-center gap-2"
            >
              <Play size={20} />
              Start Scraper
            </button>
          )}
          <button
            onClick={loadStatus}
            className="bg-gray-200 text-gray-700 px-4 py-3 rounded-lg font-medium hover:bg-gray-300 transition"
          >
            <RefreshCw size={20} />
          </button>
        </div>
      </div>

      {/* Status Bar */}
      <div className={`rounded-xl p-4 text-white ${
        status?.is_running 
          ? 'bg-gradient-to-r from-green-500 to-blue-500' 
          : 'bg-gradient-to-r from-gray-500 to-gray-600'
      }`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {status?.is_running ? (
              <>
                <div className="w-3 h-3 bg-white rounded-full animate-pulse"></div>
                <span className="font-semibold text-lg">Live Scraping Active</span>
              </>
            ) : (
              <>
                <div className="w-3 h-3 bg-gray-300 rounded-full"></div>
                <span className="font-semibold text-lg">Scraper Idle</span>
              </>
            )}
          </div>
          <div className="text-right text-sm">
            <div>Started: {formatTime(status?.start_time)}</div>
            <div>Elapsed: {formatElapsed(status?.elapsed_seconds)}</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Browser Screenshot */}
        <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-gray-100 p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Camera size={20} className="text-blue-500" />
              Browser View
            </h2>
            <div className="flex items-center gap-2 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                  className="rounded"
                />
                Auto-refresh
              </label>
              <select
                value={refreshInterval}
                onChange={(e) => setRefreshInterval(Number(e.target.value))}
                className="border rounded px-2 py-1 text-sm"
                disabled={!autoRefresh}
              >
                <option value={1}>1s</option>
                <option value={2}>2s</option>
                <option value={5}>5s</option>
                <option value={10}>10s</option>
              </select>
            </div>
          </div>
          
          {/* Screenshot Display */}
          <div className="bg-gray-900 rounded-lg overflow-hidden" style={{ aspectRatio: '16/10' }}>
            {status?.screenshot ? (
              <img
                src={`data:image/png;base64,${status.screenshot}`}
                alt="Browser screenshot"
                className="w-full h-full object-contain"
              />
            ) : (
              <div className="flex items-center justify-center h-full text-gray-400">
                <div className="text-center">
                  <Globe size={64} className="mx-auto mb-4 opacity-50" />
                  <p className="text-lg">No active browser</p>
                  <p className="text-sm">Start the scraper to see live browser view</p>
                </div>
              </div>
            )}
          </div>

          {/* Current Status */}
          {status?.is_running && (
            <div className="mt-4 p-3 bg-blue-50 rounded-lg">
              <div className="flex items-center gap-2 text-blue-900 font-medium mb-1">
                <Activity size={16} />
                Current Action:
              </div>
              <div className="text-blue-800 text-sm">{status.current_action}</div>
              {status.current_url && (
                <div className="text-blue-600 text-xs mt-1 truncate font-mono">
                  {status.current_url}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Sidebar - Stats & Activity */}
        <div className="space-y-4">
          {/* Stats Card */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <h3 className="font-semibold mb-3 flex items-center gap-2">
              <CheckCircle size={18} className="text-green-500" />
              Session Stats
            </h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-gray-600 text-sm">Current Portal</span>
                <span className="font-medium">{status?.current_portal || 'None'}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-600 text-sm">Jobs Found</span>
                <span className="font-bold text-green-600 text-lg">
                  {status?.total_jobs_scraped || 0}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-600 text-sm">Actions Logged</span>
                <span className="font-medium">{status?.action_log?.length || 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-gray-600 text-sm">Last Update</span>
                <span className="text-xs text-gray-500">
                  {formatTime(status?.last_update)}
                </span>
              </div>
            </div>
          </div>

          {/* Recent Jobs */}
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
            <h3 className="font-semibold mb-3 flex items-center gap-2">
              <Building2 size={18} className="text-purple-500" />
              Recent Jobs Found
            </h3>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {status?.jobs_found?.length > 0 ? (
                status.jobs_found.slice(-10).reverse().map((job, idx) => (
                  <div key={idx} className="p-2 bg-gray-50 rounded text-sm">
                    <div className="font-medium text-gray-900 truncate">{job.title}</div>
                    <div className="text-gray-500 text-xs">{job.company}</div>
                    <div className="text-gray-400 text-xs">{formatTime(job.time)}</div>
                  </div>
                ))
              ) : (
                <p className="text-gray-400 text-sm text-center py-4">No jobs yet</p>
              )}
            </div>
          </div>

          {/* Errors */}
          {status?.errors?.length > 0 && (
            <div className="bg-white rounded-xl shadow-sm border border-red-200 p-4">
              <h3 className="font-semibold mb-3 flex items-center gap-2 text-red-600">
                <AlertCircle size={18} />
                Errors
              </h3>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {status.errors.slice(-5).reverse().map((err, idx) => (
                  <div key={idx} className="p-2 bg-red-50 rounded text-xs text-red-700">
                    {err.error}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Activity Log */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-4">
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Activity size={20} className="text-orange-500" />
          Activity Log
        </h2>
        <div className="bg-gray-900 rounded-lg p-3 max-h-64 overflow-y-auto font-mono text-sm">
          {status?.action_log?.length > 0 ? (
            status.action_log.map((log, idx) => (
              <div key={idx} className="text-gray-300 py-1">
                <span className="text-gray-500">[{formatTime(log.time)}]</span>{' '}
                <span className="text-blue-400">{log.portal || 'system'}</span>{' '}
                <span>→ {log.action}</span>
              </div>
            ))
          ) : (
            <div className="text-gray-500 text-center py-4">
              No activity yet. Start the scraper to see logs.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
