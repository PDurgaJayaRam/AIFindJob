import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { getToken } from '../lib/api.js';

export default function JobCard({ job, index = 0 }) {
  const [showActions, setShowActions] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [findingContacts, setFindingContacts] = useState(false);
  const [resumeUrl, setResumeUrl] = useState(null);
  const [contacts, setContacts] = useState(null);
  const [showContacts, setShowContacts] = useState(false);

  const skills = Array.isArray(job.skills_required) ? job.skills_required.slice(0, 6) : [];
  const matchScore = job.match?.score ?? job.ats_score ?? 0;

  const handleGenerateResume = async () => {
    // Check for authentication first
    const token = getToken();
    if (!token) {
      if (confirm('Please sign in to generate resumes. Go to login page?')) {
        window.location.href = '/login';
      }
      return;
    }

    // Check if job has an ID
    if (!job?.id) {
      alert('Cannot generate resume: Job has no ID');
      return;
    }

    setGenerating(true);
    try {
      console.log('Generating resume for job:', job.id);
      const data = await (await import('../lib/api.js')).generateResume(job.id);
      console.log('Resume response:', data);
      setResumeUrl(data.download_url);
      
      // Use fetch to download since window.open won't include auth header
      // The download URL works with auth header or returns the file directly
      const response = await fetch(data.download_url, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      if (!response.ok) {
        throw new Error(`${response.status} ${await response.text()}`);
      }
      const blob = await response.blob();
      
      // Determine file extension based on content type
      const contentType = response.headers.get('content-type') || '';
      const isPDF = contentType.includes('pdf') || data.pdf_available;
      const fileExt = isPDF ? 'pdf' : 'docx';
      
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `tailored_resume_${job.id}.${fileExt}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      // Show success message
      alert(`Resume generated successfully! (${isPDF ? 'PDF' : 'DOCX'} format)\nPreview: ${data.preview?.substring(0, 150)}...`);
    } catch (err) {
      console.error('Resume error:', err);
      if (err.message.includes('401')) {
        if (confirm('Authentication required. Please sign in again?')) {
          window.location.href = '/login';
        }
      } else {
        alert('Could not generate resume: ' + err.message);
      }
    } finally {
      setGenerating(false);
    }
  };

  const handleFindContacts = async () => {
    // Check for authentication first
    const token = getToken();
    if (!token) {
      if (confirm('Please sign in to find contacts. Go to login page?')) {
        window.location.href = '/login';
      }
      return;
    }

    setFindingContacts(true);
    try {
      const data = await (await import('../lib/api.js')).findContacts(job.id);
      setContacts(data);
      setShowContacts(true);
    } catch (err) {
      if (err.message.includes('401')) {
        if (confirm('Authentication required. Please sign in again?')) {
          window.location.href = '/login';
        }
      } else {
        alert('Could not find contacts: ' + err.message);
      }
    } finally {
      setFindingContacts(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4, delay: Math.min(index * 0.04, 0.4), ease: [0.16, 1, 0.3, 1] }}
      className="glass rounded-2xl p-5 block hover:border-aqua/40 group ease-elastic"
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className="text-lg font-semibold text-white">{job.title}</h3>
        <span className="text-[10px] uppercase tracking-wider text-aqua/80 border border-aqua/30 rounded-full px-2 py-0.5 ease-elastic">
          {job.source}
        </span>
      </div>
      <p className="text-sm text-gray-300 mt-1">
        {job.company || 'Unknown company'} · {job.location || 'Remote'}
      </p>

      {/* Match score badge */}
      {matchScore > 0 && (
        <div className="mt-3 inline-flex items-center gap-2">
          <span className="text-xs text-nebula">Match:</span>
          <div className="flex-1 h-2 bg-white/[0.02] border border-white/[0.07] rounded-full overflow-hidden w-24">
            <div
              className="h-full bg-gradient-to-r from-nebula to-aqua transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
              style={{ width: `${Math.min(matchScore, 100)}%` }}
            />
          </div>
          <span className="text-xs font-bold text-aqua">{Math.round(matchScore)}%</span>
        </div>
      )}

      {skills.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {skills.map((s) => (
            <span key={s} className="text-xs text-nebula/90 bg-nebula/10 rounded-md px-2 py-0.5 ease-elastic">
              {s}
            </span>
          ))}
        </div>
      )}

      {/* Contacts Display */}
      {showContacts && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-3 p-3 bg-white/[0.02] border border-white/[0.07] rounded-lg"
        >
          <div className="flex items-center justify-between mb-2">
            <p className="text-aqua text-xs font-medium">
              👥 {contacts?.contacts?.length > 0 ? `${contacts.contacts.length} contacts found` : 'No contacts found'}
            </p>
            <button
              onClick={() => setShowContacts(false)}
              className="text-gray-500 text-xs hover:text-gray-300"
            >
              ✕
            </button>
          </div>
          {contacts?.contacts?.length > 0 ? (
            <div className="space-y-1.5 max-h-96 overflow-y-auto">
              {contacts.contacts.map((contact, idx) => (
                <div key={idx} className="text-xs">
                  <span className="text-gray-400">{contact.name || 'Unknown'}:</span>
                  <span className="text-nebula ml-1 font-mono">{contact.email}</span>
                  <span className={`ml-2 text-[10px] px-1.5 py-0.5 rounded ${
                    contact.confidence >= 0.5 ? 'bg-green-500/20 text-green-300' : 'bg-amber-500/20 text-amber-300'
                  }`}>
                    {Math.round(contact.confidence * 100)}%
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[10px] text-gray-500">
              Inferred emails are guesses. Verify before sending.
            </p>
          )}
        </motion.div>
      )}

      {/* Missing Skills / Learning Recommendations */}
      {job.match?.missing_skills?.length > 0 && (
        <div className="mt-3 p-3 bg-amber-500/5 border border-amber-500/20 rounded-lg">
          <p className="text-amber-300 text-xs font-medium mb-1.5">🔍 Skills to Learn:</p>
          <div className="flex flex-wrap gap-1">
            {job.match.missing_skills.map((s) => (
              <span key={s} className="text-xs text-amber-400/80 bg-amber-500/10 rounded px-1.5 py-0.5 ease-elastic">
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Action buttons - appear on hover - always show Resume and Contacts buttons */}
      <AnimatePresence>
        {showActions && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="mt-4 pt-3 border-t border-white/[0.07] flex gap-2"
          >
            <button
              onClick={handleGenerateResume}
              disabled={generating}
              className="flex-1 px-3 py-1.5 bg-gradient-to-r from-nebula/20 to-aqua/20 text-aqua rounded-lg text-xs font-medium hover:from-nebula/30 hover:to-aqua/30 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
            >
              {generating ? 'Generating...' : '📝 Resume'}
            </button>
            <button
              onClick={handleFindContacts}
              disabled={findingContacts || generating}
              className="flex-1 px-3 py-1.5 bg-white/[0.02] border border-white/[0.07] text-gray-300 rounded-lg text-xs font-medium hover:bg-white/[0.04] transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
            >
              {findingContacts ? 'Finding...' : '👥 Contacts'}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
