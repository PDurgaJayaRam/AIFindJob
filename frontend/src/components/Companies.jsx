import React, { useState } from 'react'
import axios from 'axios'
import { 
  Building2, 
  Search, 
  ExternalLink, 
  Star, 
  TrendingUp,
  Users,
  Globe,
  Loader2
} from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function Companies() {
  const [searchTerm, setSearchTerm] = useState('')
  const [companies, setCompanies] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedCompany, setSelectedCompany] = useState(null)

  const searchCompanies = async () => {
    if (!searchTerm.trim()) return
    
    setLoading(true)
    try {
      const response = await axios.post(`${API}/company-research/batch`, 
        [searchTerm],
        { headers: { 'Content-Type': 'application/json' } }
      )
      setCompanies(response.data.companies || [])
    } catch (error) {
      console.error('Error searching companies:', error)
      alert('Error: ' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Company Research</h1>
        <p className="text-gray-500 mt-1">Deep research on companies - size, tech stack, culture, and more</p>
      </div>

      {/* Search */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <div className="flex gap-4">
          <input
            type="text"
            placeholder="Enter company name (e.g., Google, TCS, Infosys)"
            className="flex-1 border rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && searchCompanies()}
          />
          <button
            onClick={searchCompanies}
            disabled={loading || !searchTerm.trim()}
            className="bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50 flex items-center gap-2"
          >
            {loading ? (
              <Loader2 size={20} className="animate-spin" />
            ) : (
              <Search size={20} />
            )}
            Research
          </button>
        </div>
      </div>

      {/* Results */}
      {companies.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {companies.map((company, idx) => (
            <div 
              key={idx} 
              className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 hover:shadow-md transition cursor-pointer"
              onClick={() => setSelectedCompany(company)}
            >
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-xl font-semibold text-gray-900">{company.name}</h3>
                  <p className="text-sm text-gray-500">{company.industry}</p>
                </div>
                <div className="flex items-center gap-1">
                  <Star size={16} className="text-yellow-500 fill-yellow-500" />
                  <span className="font-medium">{company.glassdoor_rating || 'N/A'}</span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <Users size={16} className="text-gray-400" />
                  {company.size || 'Unknown'} employees
                </div>
                <div className="flex items-center gap-2 text-sm text-gray-600">
                  <TrendingUp size={16} className="text-gray-400" />
                  {company.funding_stage || 'Unknown'}
                </div>
              </div>

              <div className="mb-4">
                <div className="text-sm font-medium text-gray-700 mb-2">Tech Stack:</div>
                <div className="flex flex-wrap gap-2">
                  {(company.tech_stack || []).slice(0, 5).map((tech, i) => (
                    <span key={i} className="px-2 py-1 bg-blue-100 text-blue-800 rounded text-xs">
                      {tech}
                    </span>
                  ))}
                  {(company.tech_stack || []).length > 5 && (
                    <span className="px-2 py-1 bg-gray-100 text-gray-600 rounded text-xs">
                      +{company.tech_stack.length - 5} more
                    </span>
                  )}
                </div>
              </div>

              <div className="flex items-center justify-between pt-4 border-t border-gray-100">
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    company.culture_score >= 70 ? 'bg-green-100 text-green-800' :
                    company.culture_score >= 40 ? 'bg-yellow-100 text-yellow-800' :
                    'bg-red-100 text-red-800'
                  }`}>
                    Culture: {company.culture_score || 0}%
                  </span>
                </div>
                <button className="text-blue-600 hover:text-blue-800 text-sm font-medium flex items-center gap-1">
                  View Details <ExternalLink size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {companies.length === 0 && !loading && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-12 text-center">
          <Building2 size={64} className="mx-auto mb-4 text-gray-300" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No companies researched yet</h3>
          <p className="text-gray-500 mb-6">Search for a company to get detailed insights</p>
          <div className="flex flex-wrap justify-center gap-2">
            {['Google', 'Microsoft', 'TCS', 'Infosys', 'Wipro'].map((name) => (
              <button
                key={name}
                onClick={() => { setSearchTerm(name); }}
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
