import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { fetchPoolJobs, fetchIngestionStatus, logout, getToken, seedDemoJobs } from '../lib/api.js';
import { useUserProfile } from '../context/UserProfileContext.jsx';
import JobCard from '../components/JobCard.jsx';

export default function Jobs() {
  const { profile, setProfile, setNeedsOnboarding } = useUserProfile();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [ingestionStatus, setIngestionStatus] = useState(null);
  const [seeding, setSeeding] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;

    // Check ingestion status
    fetchIngestionStatus()
      .then(status => {
        if (active) setIngestionStatus(status);
      })
      .catch(() => {});

    fetchPoolJobs({ limit: 48 })
      .then((data) => {
        if (active) setJobs(data.jobs || []);
      })
      .catch((e) => {
        if (active) setError(e.message);
        if (e.message.includes('401')) navigate('/login');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [navigate]);

  const handleGetMyMatches = () => {
    const token = getToken();
    if (!token) {
      navigate('/login');
      return;
    }
    // Navigate to matches - onboarding will be triggered there if needed
    navigate('/matches');
  };

  const handleLogout = async () => {
    try {
      await logout();
    } catch (e) {
      // Ignore errors - still clear client-side
    }
    setProfile(null);
    setNeedsOnboarding(false);
    navigate('/login');
  };

  const handleSeedDemoJobs = async () => {
    setSeeding(true);
    try {
      await seedDemoJobs();
      // Refresh jobs after seeding
      const data = await fetchPoolJobs({ limit: 48 });
      setJobs(data.jobs || []);
    } catch (e) {
      setError(`Failed to seed demo jobs: ${e.message}`);
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div className="min-h-screen px-6 md:px-12 py-8">
      <div className="flex items-center justify-between mb-8">
        <Link to="/" className="font-semibold text-white">
          JOB<span className="text-aqua">Finder</span>
        </Link>
        <div className="flex gap-4 text-sm">
          <Link to="/" className="text-gray-300 hover:text-white">Home</Link>
          {profile ? (
            <>
              <button
                onClick={() => navigate('/matches')}
                className="glass rounded-full px-4 py-1.5 hover:border-aqua/40 text-white"
              >
                My Matches
              </button>
              <span className="glass rounded-full px-4 py-1.5">
                {profile.name || profile.email || 'Account'}
              </span>
              <button
                onClick={handleLogout}
                className="text-gray-400 hover:text-white transition-colors"
              >
                Sign out
              </button>
            </>
          ) : (
            <Link to="/login" className="glass rounded-full px-4 py-1.5 hover:border-aqua/40">
              Sign in
            </Link>
          )}
        </div>
      </div>

      <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">Live job pool</h1>
      <p className="text-gray-400 mb-8">
        Jobs collected by the 24/7 ingestion engine.
      </p>

      {/* Cinematic Loading State */}
      {loading && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex flex-col items-center justify-center py-20"
        >
          <div className="relative mb-8">
            <div className="w-20 h-20 border-4 border-nebula/30 border-t-aqua rounded-full animate-spin" />
            <div className="absolute -inset-4 w-28 h-28 border-2 border-aqua/20 rounded-full animate-pulse" />
          </div>
          <h2 className="text-3xl font-bold text-white mb-3">
            WAIT — WE ARE GETTING DATA
          </h2>
          <p className="text-gray-300 text-center max-w-md">
            Our AI agents are collecting the best jobs for you across multiple sources.
          </p>
          {ingestionStatus?.sources && (
            <div className="mt-6 flex flex-wrap gap-2 justify-center">
              {ingestionStatus.sources.map(s => (
                <span
                  key={s.name}
                  className={`text-xs px-3 py-1 rounded-full ${
                    s.ok ? 'bg-aqua/20 text-aqua' : 'bg-amber-500/20 text-amber-400'
                  }`}
                >
                  {s.name}: {s.jobs_fetched || 0} jobs
                </span>
              ))}
            </div>
          )}
        </motion.div>
      )}

      {error && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass rounded-xl p-4 text-amber-300 max-w-md mx-auto mb-6"
        >
          Could not load jobs: {error}
          <br />
          <span className="text-gray-400 text-sm">Is the backend running on :8000?</span>
        </motion.div>
      )}

      {!loading && !error && jobs.length === 0 && (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center justify-center py-20"
        >
          <h2 className="text-3xl font-bold text-white mb-3">WAIT — WE ARE GETTING DATA</h2>
          <p className="text-gray-300 mb-6">The job pool is empty. Trigger ingestion in the admin panel.</p>
          <Link
            to="/admin"
            className="glass rounded-full px-6 py-2.5 text-aqua hover:border-aqua/40"
          >
            Go to Admin Panel
          </Link>
        </motion.div>
      )}

      {!loading && !error && jobs.length > 0 && (
        <>
          {/* Show low relevance warning and demo seed option */}
          {ingestionStatus?.sources && !ingestionStatus.sources.some(s => s.name?.includes('naukri') || s.name?.includes('india')) && (
            <div className="glass rounded-xl p-4 mb-6 border border-amber-500/30">
              <p className="text-amber-300 text-sm mb-3">
                ⚠️ Low relevance jobs shown. Use demo mode to see India tech jobs.
              </p>
              <button
                onClick={handleSeedDemoJobs}
                disabled={seeding}
                className="px-4 py-2 bg-gradient-to-r from-nebula to-aqua text-ink rounded-full text-sm font-semibold hover:opacity-90 disabled:opacity-50"
              >
                {seeding ? 'Adding jobs…' : 'Seed Demo Tech Jobs'}
              </button>
            </div>
          )}

          <div className="mb-6 flex justify-end">
            <button
              onClick={handleGetMyMatches}
              className="bg-gradient-to-r from-nebula to-aqua text-ink font-semibold rounded-full px-6 py-2.5 hover:opacity-90"
            >
              Find My Matching Jobs
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {jobs.map((job, i) => (
              <JobCard key={job.id ?? i} job={job} index={i} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
