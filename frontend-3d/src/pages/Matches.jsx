import React, { useEffect, useState, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { fetchMyMatches, fetchIngestionStatus, logout, getToken, seedDemoJobs } from '../lib/api.js';
import { useUserProfile } from '../context/UserProfileContext.jsx';
import OnboardingDialog from '../components/OnboardingDialog.jsx';
import JobCard from '../components/JobCard.jsx';

export default function Matches() {
  const { profile, needsOnboarding, loading, setProfile, setNeedsOnboarding, completeOnboarding } = useUserProfile();
  const [matches, setMatches] = useState([]);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState('');
  const [ingestionStatus, setIngestionStatus] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const navigate = useNavigate();

  // Debug: Check token on mount
  useEffect(() => {
    const token = getToken();
    console.log('Token on mount:', token ? `exists (${token.substring(0, 20)}...)` : 'none');
  }, []);

  // Trigger a refresh by changing the key
  const triggerRefresh = useCallback(() => {
    setRefreshKey(k => k + 1);
    setFetching(true);
    setError('');
  }, []);

  useEffect(() => {
    if (loading) return;

    // If no token, redirect to login
    const token = getToken();
    if (!token) {
      navigate('/login');
      return;
    }

    let active = true;

    // Always fetch ingestion status regardless of onboarding state
    fetchIngestionStatus()
      .then(status => {
        if (active) setIngestionStatus(status);
      })
      .catch(() => {});

    // If we have a valid token and profile loaded, fetch matches
    // Even if needsOnboarding is true, try to fetch matches (they'll just have lower scores)
    if (token && !needsOnboarding) {
      console.log('Fetching matches, needsOnboarding:', needsOnboarding, 'profile:', !!profile);
      fetchMyMatches({ limit: 48 })
        .then((data) => {
          if (active) {
            const matchedJobs = data.matches || [];
            setMatches(matchedJobs);
            setError('');
          }
        })
        .catch((e) => {
          if (active) setError(e.message);
          console.error('fetchMyMatches error:', e.message);
          if (e.message.includes('401')) {
            navigate('/login');
          }
        })
        .finally(() => {
          if (active) setFetching(false);
        });
    } else if (token && needsOnboarding) {
      // Need to complete onboarding - but still set fetching to false
      setFetching(false);
      console.log('Needs onboarding - showing dialog');
    } else {
      setFetching(false);
    }

    return () => {
      active = false;
    };
  }, [loading, needsOnboarding, refreshKey, navigate, profile]);

  // Handle when profile becomes null (after logout)
  useEffect(() => {
    if (!loading && !profile) {
      // If no profile and we have jobs, clear them
      if (matches.length > 0) {
        setMatches([]);
      }
    }
  }, [profile, loading, matches.length]);

  const handleOnboardingComplete = useCallback((profileData) => {
    if (profileData) {
      completeOnboarding(profileData);
      // Re-fetch matches after profile is set up
      // Use timeout to ensure context state updates first
      setTimeout(() => {
        setRefreshKey(k => k + 1);
      }, 100);
    } else {
      setNeedsOnboarding(false);
      setRefreshKey(k => k + 1);
    }
  }, [completeOnboarding, setNeedsOnboarding]);

  const handleLogout = useCallback(async () => {
    try {
      await logout();
    } catch (e) {
      // Ignore errors - we still clear the token client-side
    }
    // Clear profile state and redirect to login
    setProfile(null);
    setNeedsOnboarding(false);
    navigate('/login');
  }, [navigate, setProfile, setNeedsOnboarding]);

  const showLoadingMessage = fetching && matches.length === 0 && !error;

  // Debug: Log state changes
  useEffect(() => {
    console.log('Matches state:', { 
      loading, 
      needsOnboarding, 
      fetching, 
      matchesCount: matches.length, 
      error, 
      profile: profile ? 'exists' : 'null' 
    });
  }, [loading, needsOnboarding, fetching, matches.length, error, profile]);

  // Try to seed demo jobs if pool is low and no auth error
  useEffect(() => {
    if (error && !error.includes('401') && !error.includes('No resume') && matches.length === 0) {
      // Auto-seed demo jobs on error (likely backend issues)
      seedDemoJobs().catch(() => {});
    }
  }, [error]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-nebula/30 border-t-aqua rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-300">Loading your profile...</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <AnimatePresence>
        {needsOnboarding && (
          <OnboardingDialog onComplete={handleOnboardingComplete} />
        )}
      </AnimatePresence>

      <div className="min-h-screen px-6 md:px-12 py-8">
        <div className="flex items-center justify-between mb-8">
          <Link to="/" className="font-semibold text-white">
            JOB<span className="text-aqua">Finder</span>
          </Link>
          <div className="flex gap-4 text-sm items-center">
            <Link to="/jobs" className="text-gray-300 hover:text-white">All jobs</Link>
            <Link to="/admin" className="text-gray-300 hover:text-white">Admin</Link>
            {profile ? (
              <>
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

        <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">Your matches</h1>
        <p className="text-gray-400 mb-8">
          Pool jobs ranked against your resume and target role.
          <button 
            onClick={triggerRefresh}
            className="ml-4 text-aqua text-xs hover:underline"
          >
            Refresh
          </button>
        </p>

        {/* Debug Info */}
        <div className="glass rounded-xl p-3 mb-4 text-xs opacity-70 hover:opacity-100 transition-opacity">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-gray-300">
            <div>loading: {String(loading)}</div>
            <div>needsOnboarding: {String(needsOnboarding)}</div>
            <div>fetching: {String(fetching)}</div>
            <div>matches: {matches.length}</div>
            <div>error: {error || 'none'}</div>
            <div>profile: {profile ? 'yes' : 'no'}</div>
            <div>refreshKey: {refreshKey}</div>
            {profile && (
              <div>target_roles: {profile.target_roles?.length || 0}</div>
            )}
          </div>
        </div>

        {showLoadingMessage && !error && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="flex flex-col items-center justify-center py-20"
          >
            <div className="relative mb-8">
              <div className="w-20 h-20 border-4 border-nebula/30 border-t-aqua rounded-full animate-spin" />
              <div className="absolute inset-0 w-20 h-20 border-4 border-transparent border-t-gradient-to-r border-t-nebula rounded-full animate-spin" style={{ animationDelay: '-0.5s' }} />
            </div>
            <h2 className="text-3xl font-bold text-white mb-3">
              WAIT — WE ARE GETTING DATA
            </h2>
            <p className="text-gray-300 text-center max-w-md">
              Our 24/7 ingestion engine is collecting jobs for you. 
              {ingestionStatus?.sources?.length > 0 && (
                <>
                  <br />
                  Active sources: {ingestionStatus.sources.map(s => s.name).join(', ')}
                </>
              )}
            </p>
            <div className="mt-6 glass rounded-full px-6 py-2">
              <span className="text-aqua">
                {matches.length > 0 ? 'Scoring your jobs...' : 'No matches yet — be the first!'}
              </span>
            </div>
          </motion.div>
        )}

        {error && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass rounded-xl p-4 max-w-md mx-auto mb-6 flex flex-col items-center"
          >
            {error.includes('401') 
              ? (
                <>
                  <p className="text-aqua text-center mb-3">Please sign in to use resume features</p>
                  <button
                    onClick={() => navigate('/login')}
                    className="px-6 py-2 bg-gradient-to-r from-nebula to-aqua text-ink font-semibold rounded-full text-sm hover:opacity-90"
                  >
                    Sign In
                  </button>
                </>
              )
              : error.includes('No resume')
              ? (
                <>
                  <p className="text-aqua text-center mb-3">Please set up your profile to see matches</p>
                  <button
                    onClick={() => setNeedsOnboarding(true)}
                    className="px-6 py-2 bg-gradient-to-r from-nebula to-aqua text-ink font-semibold rounded-full text-sm hover:opacity-90"
                  >
                    Set Up Profile
                  </button>
                </>
              )
              : (
                <p className="text-amber-300">Could not load matches: {error}</p>
              )}
          </motion.div>
        )}

        {!showLoadingMessage && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {matches.map((job, i) => (
                <div key={job.id ?? i} className="relative">
                  <motion.span
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ delay: i * 0.05 }}
                    className="absolute -top-2 -right-2 z-10 text-xs font-bold bg-gradient-to-r from-nebula to-aqua text-ink rounded-full px-2 py-0.5"
                  >
                    {Math.round(job.match?.score ?? 0)}%
                  </motion.span>
                  <JobCard job={job} index={i} />
                </div>
              ))}
            </div>
            
            {/* Empty state when no matches */}
            {matches.length === 0 && !error && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex flex-col items-center justify-center py-12 mt-4"
              >
                <p className="text-gray-400 mb-4">No matches found for your profile yet.</p>
                <button
                  onClick={() => setNeedsOnboarding(true)}
                  className="px-4 py-2 bg-gradient-to-r from-nebula/20 to-aqua/20 text-aqua rounded-full text-sm hover:from-nebula/30 hover:to-aqua/30"
                >
                  Update Your Profile
                </button>
              </motion.div>
            )}
          </>
        )}
      </div>
    </>
  );
}