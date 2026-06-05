import React, { useEffect, useState } from 'react'
import axios from 'axios'
import { 
  Briefcase, 
  Building2, 
  Users, 
  Send, 
  TrendingUp,
  Clock,
  CheckCircle,
  AlertCircle,
  Zap
} from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [pipelineStatus, setPipelineStatus] = useState(null)
  const [recentJobs, setRecentJobs] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    try {
      const [statsRes, pipelineRes, jobsRes] = await Promise.all([
        axios.get(`${API}/analytics/dashboard`).catch(() => ({ data: null })),
        axios.get(`${API}/scheduler/status`).catch(() => ({ data: null })),
        axios.get(`${API}/saved-jobs?limit=5&sort_by=newest`).catch(() => ({ data: { jobs: [] } }))
      ])
      
      setStats(statsRes.data)
      setPipelineStatus(pipelineRes.data)
      setRecentJobs(jobsRes.data.jobs || [])
    } catch (error) {
      console.error('Error loading dashboard:', error)
    } finally {
      setLoading(false)
    }
  }

  const triggerPipeline = async () => {
    try {
      await axios.post(`${API}/scheduler/trigger`)
      alert('Pipeline triggered! It will run in the background.')
    } catch (error) {
      alert('Error: ' + (error.response?.data?.detail || error.message))
    }
  }

  const statCards = [
    { 
      label: 'Jobs Found', 
      value: stats?.total_applications ?? recentJobs.length, 
      icon: Briefcase, 
      color: 'bg-blue-500',
      change: '+12 today'
    },
    { 
      label: 'Companies', 
      value: stats?.status_breakdown?.applied ?? 0, 
      icon: Building2, 
      color: 'bg-purple-500',
      change: '+3 new'
    },
    { 
      label: 'People Found', 
      value: stats?.total_outreach ?? 0, 
      icon: Users, 
      color: 'bg-green-500',
      change: '+8 today'
    },
    { 
      label: 'Outreach Sent', 
      value: stats?.status_breakdown?.sent ?? 0, 
      icon: Send, 
      color: 'bg-orange-500',
      change: '+2 new'
    },
  ]

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className="text-gray-500">Loading dashboard...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
          <p className="text-gray-500 mt-1">AI Job Agent - Smart Job Search & Outreach</p>
        </div>
        <button
          onClick={triggerPipeline}
          className="bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700 transition flex items-center gap-2"
        >
          <Zap size={20} />
          Run Pipeline Now
        </button>
      </div>

      {/* Pipeline Status */}
      <div className="bg-gradient-to-r from-blue-600 to-purple-600 rounded-xl p-6 text-white">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-semibold mb-2">Pipeline Status</h2>
            <p className="text-blue-100">
              {pipelineStatus?.status === 'active' 
                ? `✅ Running every ${pipelineStatus.interval_minutes || 30} minutes`
                : '⚠️ Pipeline not active'}
            </p>
          </div>
          <div className="text-right">
            <div className="text-3xl font-bold">
              {recentJobs.length}
            </div>
            <div className="text-blue-100">jobs found today</div>
          </div>
        </div>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {statCards.map((card) => (
          <div key={card.label} className="bg-white rounded-xl shadow-sm p-6 border border-gray-100 hover:shadow-md transition">
            <div className="flex items-center justify-between mb-4">
              <div className={`p-3 rounded-lg ${card.color} text-white`}>
                <card.icon size={24} />
              </div>
              <span className="text-sm text-green-600 font-medium">{card.change}</span>
            </div>
            <div className="text-3xl font-bold text-gray-900">{card.value}</div>
            <div className="text-sm text-gray-500 mt-1">{card.label}</div>
          </div>
        ))}
      </div>

      {/* Recent Jobs & Quick Actions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Jobs */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Clock size={20} className="text-gray-400" />
            Recent Jobs
          </h2>
          {recentJobs.length > 0 ? (
            <div className="space-y-3">
              {recentJobs.map((job, idx) => (
                <div key={idx} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition">
                  <div className="flex-1">
                    <div className="font-medium text-gray-900">{job.title}</div>
                    <div className="text-sm text-gray-500">{job.company}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-medium text-blue-600">{job.ats_score || 0}%</div>
                    <div className="text-xs text-gray-400">match</div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-gray-400">
              <Briefcase size={48} className="mx-auto mb-4 opacity-50" />
              <p>No jobs found yet. Run the pipeline to start discovering jobs!</p>
            </div>
          )}
        </div>

        {/* Quick Actions */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Zap size={20} className="text-gray-400" />
            Quick Actions
          </h2>
          <div className="space-y-3">
            <button className="w-full text-left p-4 bg-blue-50 rounded-lg hover:bg-blue-100 transition">
              <div className="font-medium text-blue-900">🔍 Run Full Pipeline</div>
              <div className="text-sm text-blue-600">Discover jobs, research companies, find people</div>
            </button>
            <button className="w-full text-left p-4 bg-green-50 rounded-lg hover:bg-green-100 transition">
              <div className="font-medium text-green-900">👥 Find People at Company</div>
              <div className="text-sm text-green-600">Discover HR, tech leads, and peers</div>
            </button>
            <button className="w-full text-left p-4 bg-purple-50 rounded-lg hover:bg-purple-100 transition">
              <div className="font-medium text-purple-900">✉️ Generate Outreach Message</div>
              <div className="text-sm text-purple-600">AI-crafted personalized messages</div>
            </button>
            <button className="w-full text-left p-4 bg-orange-50 rounded-lg hover:bg-orange-100 transition">
              <div className="font-medium text-orange-900">📊 View Analytics</div>
              <div className="text-sm text-orange-600">Track your job search progress</div>
            </button>
          </div>
        </div>
      </div>

      {/* Pipeline Stages */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <h2 className="text-lg font-semibold mb-6">Pipeline Stages</h2>
        <div className="flex items-center justify-between">
          {[
            { name: 'Discover', icon: Briefcase, color: 'bg-blue-500', status: 'active' },
            { name: 'Analyze', icon: TrendingUp, color: 'bg-purple-500', status: 'active' },
            { name: 'Research', icon: Building2, color: 'bg-green-500', status: 'active' },
            { name: 'Find People', icon: Users, color: 'bg-orange-500', status: 'active' },
            { name: 'Outreach', icon: Send, color: 'bg-red-500', status: 'active' },
          ].map((stage, idx) => (
            <React.Fragment key={stage.name}>
              <div className="flex flex-col items-center">
                <div className={`p-3 rounded-full ${stage.color} text-white mb-2`}>
                  <stage.icon size={24} />
                </div>
                <div className="text-sm font-medium text-gray-900">{stage.name}</div>
                <div className="text-xs text-green-600 flex items-center gap-1">
                  <CheckCircle size={12} />
                  Active
                </div>
              </div>
              {idx < 4 && (
                <div className="flex-1 h-1 bg-gray-200 mx-4 relative">
                  <div className="absolute inset-0 bg-green-500 rounded-full"></div>
                </div>
              )}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  )
}
