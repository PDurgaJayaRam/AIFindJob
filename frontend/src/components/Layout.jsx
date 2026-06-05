import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { 
  LayoutDashboard, 
  Briefcase, 
  Building2, 
  Users, 
  Send, 
  Settings,
  Zap,
  Eye
} from 'lucide-react'

const nav = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/jobs', icon: Briefcase, label: 'Jobs' },
  { to: '/companies', icon: Building2, label: 'Companies' },
  { to: '/people', icon: Users, label: 'People' },
  { to: '/outreach', icon: Send, label: 'Outreach' },
  { to: '/pipeline', icon: Zap, label: 'Pipeline' },
  { to: '/live', icon: Eye, label: 'Live Scraper' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

export default function Layout({ children }) {
  const { pathname } = useLocation()
  
  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 text-white flex flex-col">
        <div className="p-6 border-b border-gray-800">
          <h1 className="text-xl font-bold tracking-wide">🎯 AI Job Agent</h1>
          <p className="text-xs text-gray-400 mt-1">Smart Job Search & Outreach</p>
        </div>
        
        <nav className="flex-1 px-4 py-6 space-y-2">
          {nav.map((item) => {
            const active = pathname === item.to
            return (
              <Link
                key={item.to}
                to={item.to}
                className={
                  'flex items-center gap-3 px-4 py-3 rounded-lg transition ' +
                  (active ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-800')
                }
              >
                <item.icon size={20} />
                <span className="font-medium">{item.label}</span>
              </Link>
            )
          })}
        </nav>
        
        <div className="p-4 border-t border-gray-800">
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              <span className="text-sm font-medium">Pipeline Active</span>
            </div>
            <p className="text-xs text-gray-400">Running every 30 min</p>
          </div>
        </div>
      </aside>
      
      {/* Main Content */}
      <main className="flex-1 overflow-y-auto">
        <div className="p-8">
          {children}
        </div>
      </main>
    </div>
  )
}
