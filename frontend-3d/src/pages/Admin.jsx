import React, { useEffect, useState, useRef } from 'react';
import { Link } from 'react-router-dom';
import { fetchAdminOverview, fetchLiveScraperStatus, startLiveScraper, stopLiveScraper } from '../lib/api.js';

export default function Admin() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [liveStatus, setLiveStatus] = useState(null);
  const [liveScraperActive, setLiveScraperActive] = useState(false);
  const [scraperInterval, setScraperInterval] = useState(null);

  // Fetch admin overview (pool + sources)
  useEffect(() => {
    let active = true;
    const load = () =>
      fetchAdminOverview()
        .then((d) => active && setData(d))
        .catch((e) => active && setError(e.message));
    load();
    const id = setInterval(load, 15000); // poll every 15s
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  // Poll live scraper status when active
  useEffect(() => {
    if (!liveScraperActive) {
      if (scraperInterval) {
        clearInterval(scraperInterval);
        setScraperInterval(null);
      }
      return;
    }

    const pollStatus = () => {
      fetchLiveScraperStatus()
        .then((s) => setLiveStatus(s))
        .catch((e) => console.error('Live scraper status error:', e));
    };

    // Immediate poll
    pollStatus();
    // Then every 2 seconds
    const interval = setInterval(pollStatus, 2000);
    setScraperInterval(interval);

    return () => clearInterval(interval);
  }, [liveScraperActive]);

  const handleStartScraper = async () => {
    try {
      await startLiveScraper();
      setLiveScraperActive(true);
      setLiveStatus(null);
    } catch (e) {
      setError(`Failed to start live scraper: ${e.message}`);
    }
  };

  const handleStopScraper = async () => {
    try {
      await stopLiveScraper();
      setLiveScraperActive(false);
    } catch (e) {
      setError(`Failed to stop live scraper: ${e.message}`);
    }
  };

  const formatTime = (seconds) => {
    if (!seconds) return '0s';
    const min = Math.floor(seconds / 60);
    const sec = Math.floor(seconds % 60);
    return `${min}:${sec.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen px-6 md:px-12 py-8">
      <div className="flex items-center justify-between mb-8">
        <Link to="/" className="font-semibold text-white">JOB<span className="text-aqua">Finder</span> Admin</Link>
        <Link to="/jobs" className="text-gray-300 hover:text-white text-sm">View jobs</Link>
      </div>

      <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">Ingestion Monitor</h1>
      <p className="text-gray-400 mb-8">Live status of the 24/7 job pool and browser scraping.</p>

      {error && <div className="glass rounded-xl p-4 text-amber-300 mb-6">Could not load: {error}</div>}

      {/* Live Scraper Control */}
      <div className="glass rounded-2xl p-6 mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-white">Live Browser Scraping</h2>
          <button
            onClick={liveScraperActive ? handleStopScraper : handleStartScraper}
            disabled={false}
            className={`px-6 py-2.5 rounded-full font-semibold transition-all ${
              liveScraperActive
                ? 'bg-red-500/20 text-red-300 hover:bg-red-500/30'
                : 'bg-gradient-to-r from-nebula to-aqua text-ink hover:opacity-90'
            }`}
          >
            {liveScraperActive ? '⏹ Stop Scraping' : '▶ Start Scraping'}
          </button>
        </div>

        <div className="text-sm text-gray-400 mb-4">
          Scrapes Naukri, LinkedIn, Indeed, Glassdoor with visible browser
        </div>

        {liveStatus && liveScraperActive && (
          <div className="space-y-4">
            {/* Status Bar */}
            <div className="flex items-center gap-4 text-sm">
              <span className={`px-3 py-1 rounded-full ${liveStatus.is_running ? 'bg-green-500/20 text-green-300' : 'bg-gray-500/20 text-gray-400'}`}>
                {liveStatus.is_running ? '🟢 Running' : '🔴 Stopped'}
              </span>
              {liveStatus.current_portal && (
                <span className="text-aqua">Portal: {liveStatus.current_portal}</span>
              )}
              <span className="text-gray-300">Jobs scraped: {liveStatus.total_jobs_scraped || 0}</span>
              <span className="text-gray-300">Time: {formatTime(liveStatus.elapsed_seconds || 0)}</span>
            </div>

            {/* Current Action */}
            {liveStatus.current_action && (
              <div className="glass rounded-lg p-3">
                <span className="text-aqua font-medium">Action: </span>
                <span className="text-white">{liveStatus.current_action}</span>
              </div>
            )}

            {/* Screenshot */}
            {liveStatus.screenshot && (
              <div className="relative">
                <img
                  src={`data:image/jpeg;base64,${liveStatus.screenshot}`}
                  alt="Live scraping screenshot"
                  className="w-full rounded-lg border border-white/10 max-h-96 object-contain bg-black/50"
                />
                <div className="absolute top-2 right-2 px-2 py-1 bg-black/60 rounded text-xs text-aqua">
                  Live View
                </div>
              </div>
            )}

            {/* Recent Jobs */}
            {liveStatus.jobs_found && liveStatus.jobs_found.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-aqua mb-2">Recent Jobs Found:</h3>
                <div className="flex flex-col gap-2 max-h-40 overflow-y-auto">
                  {liveStatus.jobs_found.slice(-5).reverse().map((job, i) => (
                    <div key={i} className="glass rounded px-3 py-2 text-sm">
                      <span className="text-white font-medium">{job.title}</span>
                      <span className="text-gray-400"> @ {job.company}</span>
                      <span className="text-nebula text-xs ml-2">({job.portal})</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Errors */}
            {liveStatus.errors && liveStatus.errors.length > 0 && (
              <div className="glass rounded-lg p-3 border border-red-500/30">
                <span className="text-red-300 font-medium">Errors: </span>
                <span className="text-gray-300 text-sm">
                  {liveStatus.errors.slice(-3).map(e => e.error).join(', ')}
                </span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Pool Stats */}
      {data && (
        <>
          <div className="glass rounded-2xl p-6 mb-8">
            <p className="text-gray-400 text-sm">Total jobs in pool</p>
            <p className="text-4xl font-bold text-white">{data.pool?.total_jobs ?? 0}</p>
            <div className="flex flex-wrap gap-2 mt-4">
              {Object.entries(data.pool?.by_source || {}).map(([src, cnt]) => (
                <span key={src} className="text-sm text-aqua/90 bg-aqua/10 rounded-md px-3 py-1">
                  {src}: {cnt}
                </span>
              ))}
            </div>
          </div>

          <h2 className="text-lg font-semibold text-white mb-3">Sources</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {(data.sources || []).map((s) => (
              <div key={s.name} className="glass rounded-xl p-4">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-white">{s.name}</span>
                  <span className={`text-xs rounded-full px-2 py-0.5 ${s.ok ? 'bg-green-500/20 text-green-300' : 'bg-red-500/20 text-red-300'}`}>
                    {s.ok ? 'OK' : 'FAILING'}
                  </span>
                </div>
                <p className="text-sm text-gray-400 mt-2">Last run: {s.last_run || 'never'}</p>
                <p className="text-sm text-gray-400">Fetched: {s.jobs_fetched} · New: {s.jobs_new}</p>
                {s.last_error && <p className="text-xs text-amber-300 mt-1">Error: {s.last_error}</p>}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}