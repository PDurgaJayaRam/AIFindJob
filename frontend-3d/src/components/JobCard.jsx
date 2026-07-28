import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { getToken, checkLinkedInStatus, linkedinLogin } from '../lib/api.js';

const CONTACT_TYPE_COLORS = {
  recruiter: { bg: 'bg-purple-500/20', text: 'text-purple-300', label: 'Recruiter' },
  hiring_manager: { bg: 'bg-blue-500/20', text: 'text-blue-300', label: 'Hiring Manager' },
  hr: { bg: 'bg-pink-500/20', text: 'text-pink-300', label: 'HR' },
  peer: { bg: 'bg-teal-500/20', text: 'text-teal-300', label: 'Peer' },
  unknown: { bg: 'bg-gray-500/20', text: 'text-gray-400', label: '' },
};

const RELEVANCE_COLORS = {
  high: 'bg-green-500/20 text-green-300',
  medium: 'bg-yellow-500/20 text-yellow-300',
  low: 'bg-gray-500/20 text-gray-400',
};

function ContactCard({ contact, unverified = false }) {
  const [showOutreach, setShowOutreach] = useState(false);
  const [copiedLinkedin, setCopiedLinkedin] = useState(false);
  const [copiedEmail, setCopiedEmail] = useState(false);

  const typeStyle = CONTACT_TYPE_COLORS[contact.contact_type] || CONTACT_TYPE_COLORS.unknown;

  const copyToClipboard = async (text, type) => {
    try {
      await navigator.clipboard.writeText(text);
      if (type === 'linkedin') { setCopiedLinkedin(true); setTimeout(() => setCopiedLinkedin(false), 2000); }
      if (type === 'email') { setCopiedEmail(true); setTimeout(() => setCopiedEmail(false), 2000); }
    } catch {
      // Fallback
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
  };

  return (
    <div className={`text-xs p-2.5 rounded-lg border ${unverified ? 'bg-white/[0.01] border-white/[0.05] opacity-70' : 'bg-green-500/5 border-green-500/10'}`}>
      {/* Header: Name + Badges */}
      <div className="flex items-center gap-2 mb-1 flex-wrap">
        {contact.linkedin_url ? (
          <a href={contact.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 underline font-medium">
            {contact.name || 'Contact'}
          </a>
        ) : (
          <span className="text-gray-300 font-medium">{contact.name || 'Contact'}</span>
        )}
        {typeStyle.label && (
          <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${typeStyle.bg} ${typeStyle.text}`}>
            {typeStyle.label}
          </span>
        )}
        {contact.relevance && contact.relevance !== 'low' && (
          <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${RELEVANCE_COLORS[contact.relevance]}`}>
            {contact.relevance} relevance
          </span>
        )}
      </div>

      {/* Role */}
      {contact.role && (
        <p className="text-gray-400 text-[10px] mb-1">{contact.role}</p>
      )}

      {/* Contact Methods */}
      <div className="flex flex-wrap gap-3 text-[10px] text-gray-400 mb-1">
        {contact.email && (
          <a href={`mailto:${contact.email}`} className="hover:text-aqua transition-colors">
            ✉ {contact.email}
          </a>
        )}
        {contact.phone && (
          <a href={`tel:${contact.phone}`} className="hover:text-aqua transition-colors">
            ☎ {contact.phone}
          </a>
        )}
        {contact.linkedin_url && (
          <a href={contact.linkedin_url} target="_blank" rel="noopener noreferrer" className="hover:text-blue-300 transition-colors">
            in/{contact.linkedin_url.split('/in/')[1] || ''}
          </a>
        )}
      </div>

      {/* Outreach Drafts Toggle */}
      {(contact.outreach_linkedin || contact.outreach_email_body) && (
        <button
          onClick={() => setShowOutreach(!showOutreach)}
          className="text-[10px] text-aqua/70 hover:text-aqua transition-colors mt-1"
        >
          {showOutreach ? '▾ Hide outreach drafts' : '▸ Show outreach drafts'}
        </button>
      )}

      {/* Outreach Drafts */}
      <AnimatePresence>
        {showOutreach && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mt-2 space-y-2 overflow-hidden"
          >
            {/* LinkedIn Message */}
            {contact.outreach_linkedin && (
              <div className="p-2 bg-blue-500/5 border border-blue-500/10 rounded">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[9px] text-blue-300 font-medium">LinkedIn Message</span>
                  <button
                    onClick={() => copyToClipboard(contact.outreach_linkedin, 'linkedin')}
                    className="text-[9px] text-blue-400 hover:text-blue-300"
                  >
                    {copiedLinkedin ? '✓ Copied' : 'Copy'}
                  </button>
                </div>
                <p className="text-[10px] text-gray-400 leading-relaxed">{contact.outreach_linkedin}</p>
              </div>
            )}

            {/* Email Draft */}
            {contact.outreach_email_body && (
              <div className="p-2 bg-amber-500/5 border border-amber-500/10 rounded">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[9px] text-amber-300 font-medium">
                    Email{contact.outreach_email_subject ? `: ${contact.outreach_email_subject}` : ''}
                  </span>
                  <button
                    onClick={() => copyToClipboard(
                      `Subject: ${contact.outreach_email_subject}\n\n${contact.outreach_email_body}`,
                      'email'
                    )}
                    className="text-[9px] text-amber-400 hover:text-amber-300"
                  >
                    {copiedEmail ? '✓ Copied' : 'Copy'}
                  </button>
                </div>
                <p className="text-[10px] text-gray-400 leading-relaxed whitespace-pre-line">{contact.outreach_email_body}</p>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function LinkedInLoginButton({ onLoginComplete }) {
  const [status, setStatus] = useState(null); // null | 'checking' | 'logged_in' | 'logging_in'
  const [message, setMessage] = useState('');

  useEffect(() => {
    checkLinkedInStatus()
      .then(data => {
        setStatus(data.valid ? 'logged_in' : 'needs_login');
        setMessage(data.message);
      })
      .catch(() => setStatus('needs_login'));
  }, []);

  const handleLogin = async () => {
    setStatus('logging_in');
    setMessage('Opening LinkedIn login... Please complete login in the browser window.');
    try {
      const result = await linkedinLogin();
      if (result.success) {
        setStatus('logged_in');
        setMessage('LinkedIn logged in successfully!');
        if (onLoginComplete) onLoginComplete();
      }
    } catch (err) {
      setStatus('needs_login');
      setMessage(err.message || 'Login failed. Please try again.');
    }
  };

  if (status === 'logged_in') {
    return (
      <p className="text-[10px] text-green-400">✓ LinkedIn connected</p>
    );
  }

  if (status === 'logging_in') {
    return (
      <div className="text-center">
        <p className="text-[10px] text-amber-300 mb-1">{message}</p>
        <div className="inline-block w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <button
      onClick={handleLogin}
      className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-[10px] rounded-lg transition-colors"
    >
      Login to LinkedIn
    </button>
  );
}

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
      const api = await import('../lib/api.js');
      
      // Generic email prefixes that are NOT real people
      const GENERIC_PREFIXES = ['hr@','careers@','hiring@','recruitment@','talent@','jobs@','info@','contact@','apply@'];
      
      // First, try to load saved contacts from database
      try {
        const savedData = await api.getSavedContacts(job.id);
        if (savedData?.contacts?.length > 0) {
          // Check if saved contacts are real people (not generic department emails)
          const realContacts = savedData.contacts.filter(c => {
            const email = (c.email || '').toLowerCase();
            const name = (c.name || '').toLowerCase();
            const isGeneric = GENERIC_PREFIXES.some(p => email.startsWith(p)) || 
                              ['hr department','careers team','hiring team','recruitment team','talent acquisition','jobs portal'].includes(name);
            return !isGeneric;
          });
          if (realContacts.length > 0) {
            savedData.contacts = realContacts;
            savedData.total_found = realContacts.length;
            setContacts(savedData);
            setShowContacts(true);
            setFindingContacts(false);
            return;
          }
          // All saved contacts are generic - re-run discovery
        }
      } catch {
        // No saved contacts, proceed with discovery
      }
      
      // No saved contacts - run full discovery
      const data = await api.findContacts(job.id);
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
          className="mt-3 p-3 bg-white/[0.02] border border-white/[0.07] rounded-lg max-h-[500px] overflow-y-auto"
        >
          <div className="flex items-center justify-between mb-2">
            <p className="text-aqua text-xs font-medium">
              {contacts?.contacts?.length > 0
                ? `People Found (${contacts.contacts.length})`
                : 'No contacts found'}
            </p>
            <button
              onClick={() => setShowContacts(false)}
              className="text-gray-500 text-xs hover:text-gray-300"
            >
              ✕
            </button>
          </div>
          {contacts?.contacts?.length > 0 ? (
            <>
              {/* Verified contacts — real people found */}
              {contacts.contacts.some(c => c.verified) && (
                <div className="mb-3">
                  <p className="text-[10px] text-green-400 mb-1.5 font-medium">
                    ✓ Verified ({contacts.verified_count || contacts.contacts.filter(c => c.verified).length})
                  </p>
                  <div className="space-y-2">
                    {contacts.contacts
                      .filter(c => c.verified)
                      .map((contact, idx) => (
                        <ContactCard key={idx} contact={contact} />
                      ))}
                  </div>
                </div>
              )}

              {/* Unverified sources */}
              {contacts.contacts.some(c => !c.verified) && (
                <div className="mb-2">
                  <p className="text-[10px] text-amber-400 mb-1.5 font-medium">
                    Other Sources ({contacts.contacts.filter(c => !c.verified).length})
                  </p>
                  <div className="space-y-2">
                    {contacts.contacts
                      .filter(c => !c.verified)
                      .slice(0, 5)
                      .map((contact, idx) => (
                        <ContactCard key={idx} contact={contact} unverified />
                      ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-2">
              <p className="text-[10px] text-gray-500 mb-2">
                No contacts found yet.
              </p>
              <div className="flex flex-col gap-2 items-center">
                <button
                  onClick={handleFindContacts}
                  className="px-3 py-1.5 bg-aqua/20 text-aqua text-[10px] rounded-lg hover:bg-aqua/30 transition-colors"
                >
                  Search for contacts
                </button>
                <LinkedInLoginButton onLoginComplete={() => handleFindContacts()} />
              </div>
            </div>
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

      {/* Action buttons - appear on hover */}
      <AnimatePresence>
        {showActions && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="mt-4 pt-3 border-t border-white/[0.07] flex gap-2"
          >
            {(job.apply_url || job.source_url) && (
              <a
                href={job.apply_url || job.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 px-3 py-1.5 bg-gradient-to-r from-amber-500/20 to-amber-400/20 text-amber-300 rounded-lg text-xs font-medium hover:from-amber-500/30 hover:to-amber-400/30 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] text-center"
              >
                Apply Now
              </a>
            )}
            <button
              onClick={handleGenerateResume}
              disabled={generating}
              className="flex-1 px-3 py-1.5 bg-gradient-to-r from-nebula/20 to-aqua/20 text-aqua rounded-lg text-xs font-medium hover:from-nebula/30 hover:to-aqua/30 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
            >
              {generating ? 'Generating...' : 'Resume'}
            </button>
            <button
              onClick={handleFindContacts}
              disabled={findingContacts || generating}
              className="flex-1 px-3 py-1.5 bg-white/[0.02] border border-white/[0.07] text-gray-300 rounded-lg text-xs font-medium hover:bg-white/[0.04] transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
            >
              {findingContacts ? 'Finding...' : 'Contacts'}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
