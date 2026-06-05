import React, { useState } from 'react'
import axios from 'axios'
import { 
  Users, 
  Search, 
  Mail, 
  Linkedin, 
  Phone,
  ExternalLink,
  Loader2,
  MessageSquare
} from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function People() {
  const [companyName, setCompanyName] = useState('')
  const [jobTitle, setJobTitle] = useState('')
  const [people, setPeople] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedPerson, setSelectedPerson] = useState(null)

  const findPeople = async () => {
    if (!companyName.trim()) return
    
    setLoading(true)
    try {
      const response = await axios.post(`${API}/find-people/${encodeURIComponent(companyName)}`, null, {
        params: { job_title: jobTitle }
      })
      setPeople(response.data.outreach_plan?.people || [])
    } catch (error) {
      console.error('Error finding people:', error)
      alert('Error: ' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  const generateMessage = async (person, type = 'linkedin') => {
    try {
      const response = await axios.post(`${API}/generate-message`, null, {
        params: {
          company_name: companyName,
          job_title: jobTitle,
          recipient_name: person.name,
          message_type: type
        }
      })
      alert(`Generated ${type} message:\n\n${response.data.message}`)
    } catch (error) {
      alert('Error: ' + (error.response?.data?.detail || error.message))
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">People Finder</h1>
        <p className="text-gray-500 mt-1">Find HR, tech leads, and peers at target companies</p>
      </div>

      {/* Search Form */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Company Name *</label>
            <input
              type="text"
              placeholder="e.g., Google, TCS"
              className="w-full border rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={companyName}
              onChange={(e) => setCompanyName(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Job Title (Optional)</label>
            <input
              type="text"
              placeholder="e.g., Software Engineer"
              className="w-full border rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={findPeople}
              disabled={loading || !companyName.trim()}
              className="w-full bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? (
                <Loader2 size={20} className="animate-spin" />
              ) : (
                <Users size={20} />
              )}
              Find People
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      {people.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-gray-900">Found {people.length} people at {companyName}</h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {people.map((person, idx) => (
              <div 
                key={idx} 
                className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition"
              >
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <h3 className="font-semibold text-gray-900">{person.name || 'Unknown'}</h3>
                    <p className="text-sm text-gray-500">{person.title || 'Employee'}</p>
                  </div>
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    person.relevance_score >= 80 ? 'bg-green-100 text-green-800' :
                    person.relevance_score >= 50 ? 'bg-yellow-100 text-yellow-800' :
                    'bg-gray-100 text-gray-600'
                  }`}>
                    {person.relevance_score || 0}% match
                  </span>
                </div>

                <div className="space-y-2 mb-4">
                  {person.email && (
                    <div className="flex items-center gap-2 text-sm text-gray-600">
                      <Mail size={14} className="text-gray-400" />
                      <span className="truncate">{person.email}</span>
                    </div>
                  )}
                  {person.linkedin && (
                    <div className="flex items-center gap-2 text-sm text-gray-600">
                      <Linkedin size={14} className="text-blue-500" />
                      <a href={person.linkedin} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline truncate">
                        LinkedIn Profile
                      </a>
                    </div>
                  )}
                  {person.phone && (
                    <div className="flex items-center gap-2 text-sm text-gray-600">
                      <Phone size={14} className="text-gray-400" />
                      <span>{person.phone}</span>
                    </div>
                  )}
                </div>

                <div className="flex gap-2">
                  <button
                    onClick={() => generateMessage(person, 'linkedin')}
                    className="flex-1 bg-blue-100 text-blue-700 px-3 py-2 rounded-lg text-sm font-medium hover:bg-blue-200 transition flex items-center justify-center gap-1"
                  >
                    <Linkedin size={14} />
                    LinkedIn
                  </button>
                  <button
                    onClick={() => generateMessage(person, 'email')}
                    className="flex-1 bg-green-100 text-green-700 px-3 py-2 rounded-lg text-sm font-medium hover:bg-green-200 transition flex items-center justify-center gap-1"
                  >
                    <Mail size={14} />
                    Email
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty State */}
      {people.length === 0 && !loading && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center">
          <Users size={64} className="mx-auto mb-4 text-gray-300" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No people found yet</h3>
          <p className="text-gray-500 mb-6">Search for a company to find employees for outreach</p>
          <div className="flex flex-wrap justify-center gap-2">
            {['Google', 'Microsoft', 'Amazon'].map((name) => (
              <button
                key={name}
                onClick={() => setCompanyName(name)}
                className="px-4 py-2 bg-gray-100 rounded-lg text-sm font-medium hover:bg-gray-200 transition"
              >
                {name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
