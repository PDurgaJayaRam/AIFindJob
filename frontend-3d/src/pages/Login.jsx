import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { login, register, setToken, getToken } from '../lib/api.js';

export default function Login() {
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fullName, setFullName] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  // If user is already logged in, show logout option
  const [hasToken, setHasToken] = useState(false);

  useEffect(() => {
    setHasToken(!!getToken());
  }, []);

  async function onSubmit(e) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const data =
        mode === 'login'
          ? await login(email, password)
          : await register(email, password, fullName);
      console.log('Login response:', data);
      console.log('Access token:', data.access_token ? data.access_token.substring(0, 30) + '...' : 'missing');
      setToken(data.access_token);
      console.log('Token saved, getting from storage:', getToken() ? 'exists' : 'missing');
      // Navigate to matches - the context will detect the new token on next mount
      navigate('/matches');
    } catch (err) {
      console.error('Login error:', err);
      setError(err.message || 'Something went wrong');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative min-h-screen flex items-center justify-center px-6 overflow-hidden">
      {/* Digital grain overlay */}
      <div className="grain-overlay" />

      {/* Deep organic blur blobs for ambient light */}
      <div className="absolute inset-0 -z-10">
        <div className="ambient-blob ambient-blob-indigo" style={{ top: '-15%', left: '-10%', width: '60vw', height: '60vw' }} />
        <div className="ambient-blob ambient-blob-teal" style={{ bottom: '-20%', right: '-15%', width: '55vw', height: '55vw' }} />
      </div>

      {/* Background glow */}
      <div className="absolute inset-0 -z-10 pointer-events-none">
        <div className="absolute top-20 left-20 w-96 h-96 bg-nebula/20 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-20 right-20 w-80 h-80 bg-aqua/10 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '-2s' }} />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-64 h-64 bg-gradient-to-r from-nebula to-aqua rounded-full blur-2xl opacity-30" />
      </div>

      <motion.form
        onSubmit={onSubmit}
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="glass rounded-3xl p-8 w-full max-w-md relative z-10 ease-elastic"
      >
        <Link to="/" className="font-semibold text-white text-lg ease-elastic">
          JOB<span className="text-aqua">Finder</span>
        </Link>
        <motion.h1
          initial={{ filter: 'blur(10px)', opacity: 0 }}
          animate={{ filter: 'blur(0px)', opacity: 1 }}
          transition={{ duration: 0.8, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          className="text-2xl md:text-3xl font-black text-white mt-4 mb-2 tracking-tighter blur-reveal"
        >
          {mode === 'login' ? 'Welcome back, seeker' : 'Start your journey'}
        </motion.h1>
        <p className="text-gray-400 mb-6 blur-reveal" style={{ animationDelay: '0.15s' }}>
          {mode === 'login' 
            ? 'Sign in to find your perfect job match' 
            : 'Create account — your AI career copilot awaits'}
        </p>

        {mode === 'register' && (
          <div>
            <label className="block text-sm font-medium text-aqua mb-2">Full name</label>
            <input
              className="w-full mb-4 rounded-xl bg-white/[0.02] border border-white/[0.07] px-4 py-3 outline-none focus:border-aqua/50 text-white transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
              placeholder="John Doe"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />
          </div>
        )}
        
        <div>
          <label className="block text-sm font-medium text-aqua mb-2">Email</label>
          <input
            type="email"
            required
            className="w-full mb-4 rounded-xl bg-white/[0.02] border border-white/[0.07] px-4 py-3 outline-none focus:border-aqua/50 text-white transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        
        <div>
          <label className="block text-sm font-medium text-aqua mb-2">Password</label>
          <input
            type="password"
            required
            className="w-full mb-6 rounded-xl bg-white/[0.02] border border-white/[0.07] px-4 py-3 outline-none focus:border-aqua/50 text-white transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        {error && (
          <motion.p
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-amber-300 text-sm mb-4 bg-amber-500/10 rounded-lg p-3"
          >
            {error}
          </motion.p>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full bg-gradient-to-r from-nebula to-aqua text-ink font-semibold rounded-xl py-3.5 text-lg hover:opacity-90 disabled:opacity-60 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
        >
          {busy ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-4 h-4 border-2 border-ink/30 border-t-ink rounded-full animate-spin" />
              Please wait…
            </span>
          ) : mode === 'login' ? 'Sign in' : 'Create account'}
        </button>

        {hasToken && (
          <button
            type="button"
            onClick={() => {
              setToken(null);
              setHasToken(false);
            }}
            className="w-full text-gray-400 text-sm mt-4 hover:text-white transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
          >
            Sign out current account
          </button>
        )}

        <button
          type="button"
          onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
          className="w-full text-gray-400 text-sm mt-6 hover:text-white transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
        >
          {mode === 'login' ? "No account? Sign up" : 'Already have an account? Sign in'}
        </button>
      </motion.form>
    </div>
  );
}
