import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { getToken } from '../lib/api.js';

export default function JobCard({ job, index = 0 }) {
  const [showActions, setShowActions] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [findingContacts, setFindingContacts] = useState(false);
  const [resumeUrl, setResumeUrl] = useState(null);

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
      window.open(data.download_url, '_blank');
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
      alert(`Found ${data.contacts?.length || 0} contacts! Check console for details.`);
      console.log('Contacts:', data);
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

      {/* Action buttons - appear on hover */}
      <AnimatePresence>
        {showActions && matchScore > 0 && (
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
              disabled={findingContacts}
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
