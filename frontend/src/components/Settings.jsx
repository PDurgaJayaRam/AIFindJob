import React, { useState, useEffect } from 'react'
import axios from 'axios'
import { 
  Settings as SettingsIcon, 
  Save, 
  Upload, 
  Loader2,
  CheckCircle
} from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function Settings() {
  const [preferences, setPreferences] = useState({
    desiredRoles: '',
    desiredLocations: '',
    skills: '',
    experienceLevel: 'fresher',
    autoApply: false
  })
  const [resume, setResume] = useState(null)
  const [resumeText, setResumeText] = useState('')
  const [loading, setLoading] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    loadPreferences()
  }, [])

  const loadPreferences = async () => {
    try {
      const response = await axios.get(`${API}/preferences`)
      const prefs = response.data
      setPreferences({
        desiredRoles: (prefs.desired_roles || []).join(', '),
        desiredLocations: (prefs.desired_locations || []).join(', '),
        skills: (prefs.skills || []).join(', '),
        experienceLevel: prefs.experience_level || 'fresher',
        autoApply: prefs.auto_apply_enabled || false
      })
    } catch (error) {
      console.log('No preferences found, using defaults')
    }
  }

  const savePreferences = async () => {
    setLoading(true)
    try {
      await axios.post(`${API}/preferences`, {
        desired_roles: preferences.desiredRoles.split(',').map(s => s.trim()).filter(Boolean),
        desired_locations: preferences.desiredLocations.split(',').map(s => s.trim()).filter(Boolean),
        skills: preferences.skills.split(',').map(s => s.trim()).filter(Boolean),
        experience_level: preferences.experienceLevel,
        auto_apply_enabled: preferences.autoApply
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (error) {
      alert('Error saving preferences: ' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  const uploadResume = async () => {
    if (!resume) return
    
    const formData = new FormData()
    formData.append('file', resume)
    
    setLoading(true)
    try {
      const response = await axios.post(`${API}/upload-resume`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
      setResumeText(response.data.text_content || '')
      alert('Resume uploaded successfully!')
    } catch (error) {
      alert('Error uploading resume: ' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Settings</h1>
        <p className="text-gray-500 mt-1">Configure your job search preferences</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Resume Upload */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Upload size={20} className="text-blue-500" />
            Upload Resume
          </h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Resume File</label>
              <input
                type="file"
                accept=".pdf,.docx,.txt"
                onChange={(e) => setResume(e.target.files[0])}
                className="w-full border rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-500 mt-1">Supported formats: PDF, DOCX, TXT</p>
            </div>
            
            {resume && (
              <button
                onClick={uploadResume}
                disabled={loading}
                className="w-full bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {loading ? (
                  <Loader2 size={20} className="animate-spin" />
                ) : (
                  <Upload size={20} />
                )}
                Upload Resume
              </button>
            )}
            
            {resumeText && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                <div className="flex items-center gap-2 text-green-800 mb-2">
                  <CheckCircle size={16} />
                  <span className="font-medium">Resume uploaded successfully</span>
                </div>
                <p className="text-sm text-green-700 truncate">{resumeText.substring(0, 100)}...</p>
              </div>
            )}
          </div>
        </div>

        {/* Job Preferences */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <SettingsIcon size={20} className="text-purple-500" />
            Job Preferences
          </h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Desired Roles (comma separated)</label>
              <input
                type="text"
                placeholder="e.g., Software Engineer, Java Developer"
                className="w-full border rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={preferences.desiredRoles}
                onChange={(e) => setPreferences({...preferences, desiredRoles: e.target.value})}
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">Desired Locations (comma separated)</label>
              <input
                type="text"
                placeholder="e.g., Hyderabad, Bangalore"
                className="w-full border rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={preferences.desiredLocations}
                onChange={(e) => setPreferences({...preferences, desiredLocations: e.target.value})}
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">Skills (comma separated)</label>
              <input
                type="text"
                placeholder="e.g., Java, Python, SQL"
                className="w-full border rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={preferences.skills}
                onChange={(e) => setPreferences({...preferences, skills: e.target.value})}
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">Experience Level</label>
              <select
                className="w-full border rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={preferences.experienceLevel}
                onChange={(e) => setPreferences({...preferences, experienceLevel: e.target.value})}
              >
                <option value="fresher">Fresher (0 years)</option>
                <option value="junior">Junior (1-3 years)</option>
                <option value="mid">Mid-level (3-5 years)</option>
                <option value="senior">Senior (5+ years)</option>
              </select>
            </div>
            
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="autoApply"
                checked={preferences.autoApply}
                onChange={(e) => setPreferences({...preferences, autoApply: e.target.checked})}
                className="w-4 h-4 text-blue-600 rounded focus:ring-blue-500"
              />
              <label htmlFor="autoApply" className="text-sm font-medium">
                Enable Auto-Apply (submit applications automatically)
              </label>
            </div>
            
            <button
              onClick={savePreferences}
              disabled={loading}
              className="w-full bg-green-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-green-700 transition disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? (
                <Loader2 size={20} className="animate-spin" />
              ) : saved ? (
                <CheckCircle size={20} />
              ) : (
                <Save size={20} />
              )}
              {saved ? 'Saved!' : 'Save Preferences'}
            </button>
          </div>
        </div>
      </div>

      {/* Info Box */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-6">
        <h3 className="font-semibold text-blue-900 mb-2">ℹ️ How It Works</h3>
        <ul className="text-sm text-blue-800 space-y-1">
          <li>• Upload your resume to extract skills and experience</li>
          <li>• Set your preferences to target specific roles and locations</li>
          <li>• The AI pipeline runs every 30 minutes to find matching jobs</li>
          <li>• It researches companies and finds people to contact</li>
          <li>• Generate personalized outreach messages with one click</li>
        </ul>
      </div>
    </div>
  )
}
