import React, { useState } from 'react'
import axios from 'axios'
import { 
  Send, 
  Mail, 
  Linkedin, 
  MessageSquare,
  Copy,
  Check,
  Loader2
} from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function Outreach() {
  const [formData, setFormData] = useState({
    companyName: '',
    jobTitle: '',
    recipientName: '',
    messageType: 'linkedin'
  })
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  const generateMessage = async () => {
    if (!formData.companyName.trim() || !formData.jobTitle.trim()) return
    
    setLoading(true)
    try {
      const response = await axios.post(`${API}/generate-message`, null, {
        params: {
          company_name: formData.companyName,
          job_title: formData.jobTitle,
          recipient_name: formData.recipientName,
          message_type: formData.messageType
        }
      })
      setMessage(response.data.message)
    } catch (error) {
      console.error('Error generating message:', error)
      alert('Error: ' + (error.response?.data?.detail || error.message))
    } finally {
      setLoading(false)
    }
  }

  const copyToClipboard = () => {
    navigator.clipboard.writeText(message)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const templates = [
    {
      name: 'LinkedIn Connection Request',
      type: 'linkedin',
      description: 'Short and professional connection request'
    },
    {
      name: 'Referral Request',
      type: 'referral',
      description: 'Ask for a referral at the company'
    },
    {
      name: 'Cold Email',
      type: 'email',
      description: 'Professional email outreach'
    },
    {
      name: 'Follow Up',
      type: 'followup',
      description: 'Follow up after no response'
    }
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Outreach</h1>
        <p className="text-gray-500 mt-1">Generate AI-crafted personalized messages for outreach</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Message Generator */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-lg font-semibold mb-4">Generate Message</h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Company Name *</label>
              <input
                type="text"
                placeholder="e.g., Google"
                className="w-full border rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={formData.companyName}
                onChange={(e) => setFormData({...formData, companyName: e.target.value})}
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">Job Title *</label>
              <input
                type="text"
                placeholder="e.g., Software Engineer"
                className="w-full border rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={formData.jobTitle}
                onChange={(e) => setFormData({...formData, jobTitle: e.target.value})}
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">Recipient Name (Optional)</label>
              <input
                type="text"
                placeholder="e.g., John Smith"
                className="w-full border rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={formData.recipientName}
                onChange={(e) => setFormData({...formData, recipientName: e.target.value})}
              />
            </div>
            
            <div>
              <label className="block text-sm font-medium mb-2">Message Type</label>
              <div className="grid grid-cols-2 gap-2">
                {templates.map((template) => (
                  <button
                    key={template.type}
                    onClick={() => setFormData({...formData, messageType: template.type})}
                    className={`p-3 rounded-lg text-left transition ${
                      formData.messageType === template.type
                        ? 'bg-blue-100 border-2 border-blue-500'
                        : 'bg-gray-50 border-2 border-transparent hover:bg-gray-100'
                    }`}
                  >
                    <div className="font-medium text-sm">{template.name}</div>
                    <div className="text-xs text-gray-500">{template.description}</div>
                  </button>
                ))}
              </div>
            </div>
            
            <button
              onClick={generateMessage}
              disabled={loading || !formData.companyName.trim() || !formData.jobTitle.trim()}
              className="w-full bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-700 transition disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? (
                <Loader2 size={20} className="animate-spin" />
              ) : (
                <Send size={20} />
              )}
              Generate Message
            </button>
          </div>
        </div>

        {/* Generated Message */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Generated Message</h2>
            {message && (
              <button
                onClick={copyToClipboard}
                className="flex items-center gap-2 px-4 py-2 bg-gray-100 rounded-lg text-sm font-medium hover:bg-gray-200 transition"
              >
                {copied ? <Check size={16} className="text-green-600" /> : <Copy size={16} />}
                {copied ? 'Copied!' : 'Copy'}
              </button>
            )}
          </div>
          
          {message ? (
            <div className="bg-gray-50 rounded-lg p-4 min-h-[200px]">
              <pre className="whitespace-pre-wrap text-sm text-gray-700 font-sans">{message}</pre>
            </div>
          ) : (
            <div className="bg-gray-50 rounded-lg p-8 text-center min-h-[200px] flex flex-col items-center justify-center">
              <MessageSquare size={48} className="text-gray-300 mb-4" />
              <p className="text-gray-500">Your generated message will appear here</p>
            </div>
          )}
          
          {message && (
            <div className="mt-4 flex gap-2">
              <button className="flex-1 bg-green-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-green-700 transition flex items-center justify-center gap-2">
                <Mail size={16} />
                Send Email
              </button>
              <button className="flex-1 bg-blue-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-blue-700 transition flex items-center justify-center gap-2">
                <Linkedin size={16} />
                Send LinkedIn
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Message Tips */}
      <div className="bg-gradient-to-r from-blue-50 to-purple-50 rounded-xl p-6 border border-blue-100">
        <h3 className="font-semibold text-gray-900 mb-3">💡 Outreach Tips</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          <div>
            <div className="font-medium text-blue-900">Personalize</div>
            <div className="text-blue-700">Mnowledge specific projects or company values</div>
          </div>
          <div>
            <div className="font-medium text-purple-900">Keep it Short</div>
            <div className="text-purple-700">3-4 sentences max for cold outreach</div>
          </div>
          <div>
            <div className="font-medium text-green-900">Follow Up</div>
            <div className="text-green-700">Send follow-up after 3-5 days if no response</div>
          </div>
        </div>
      </div>
    </div>
  )
}
