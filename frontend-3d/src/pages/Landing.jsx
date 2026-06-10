import React from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import StarField from '../three/StarField.jsx';

export default function Landing() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      <StarField />

      {/* Digital grain overlay */}
      <div className="grain-overlay" />

      {/* Deep organic blur blobs for ambient light */}
      <div className="absolute inset-0 -z-10 pointer-events-none">
        <div className="ambient-blob ambient-blob-indigo" style={{ top: '-20%', left: '-10%', width: '60vw', height: '60vw' }} />
        <div className="ambient-blob ambient-blob-teal" style={{ bottom: '-22%', right: '-8%', width: '55vw', height: '55vw' }} />
        <div className="ambient-blob ambient-blob-purple" style={{ top: '40%', left: '50%', width: '45vw', height: '45vw', transform: 'translateX(-50%)' }} />
      </div>

      {/* Hero glow effects */}
      <div className="absolute inset-0 -z-10 pointer-events-none">
        <div className="absolute top-20 left-20 w-96 h-96 bg-nebula/30 rounded-full blur-3xl" />
        <div className="absolute bottom-20 right-20 w-80 h-80 bg-aqua/20 rounded-full blur-3xl" />
      </div>

      <nav className="flex items-center justify-between px-6 md:px-12 py-5 relative z-10">
        <motion.span
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="font-semibold tracking-wide text-white text-2xl"
        >
          JOB<span className="text-aqua">Finder</span>
        </motion.span>
        <div className="flex items-center gap-4 text-sm">
          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            className="flex gap-4"
          >
            <Link to="/jobs" className="text-gray-300 hover:text-white relative group ease-elastic">
              Jobs
              <span className="absolute -bottom-1 left-0 w-0 h-px bg-aqua group-hover:w-full transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]" />
            </Link>
            <Link to="/matches" className="text-gray-300 hover:text-white relative group ease-elastic">
              Matches
              <span className="absolute -bottom-1 left-0 w-0 h-px bg-aqua group-hover:w-full transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]" />
            </Link>
            <Link to="/login" className="glass rounded-full px-6 py-2 hover:border-aqua/40 font-medium ease-elastic">
              Sign in
            </Link>
          </motion.div>
        </div>
      </nav>

      <header className="flex flex-col items-center text-center px-6 mt-24 md:mt-32 relative z-10">
        <motion.h1
          initial={{ opacity: 0, y: 30, filter: 'blur(10px)' }}
          animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          className="glow-text text-4xl md:text-7xl font-black max-w-4xl leading-tight text-white tracking-tighter blur-reveal"
        >
          Your AI career copilot for the job hunt
        </motion.h1>
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.15 }}
          className="mt-6 max-w-2xl text-gray-300 md:text-lg blur-reveal"
          style={{ animationDelay: '0.1s' }}
        >
          Discover roles matched to your resume, generate ATS-optimized resumes per job,
          and reach the right people — built for job seekers, by a job seeker.
        </motion.p>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.3 }}
          className="mt-10 flex gap-4"
        >
          <Link to="/jobs" className="bg-gradient-to-r from-nebula to-aqua text-ink font-semibold rounded-full px-8 py-3.5 hover:opacity-90 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]">
            Explore live jobs
          </Link>
          <Link to="/login" className="glass rounded-full px-8 py-3.5 hover:border-aqua/40 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]">
            Get started
          </Link>
        </motion.div>
      </header>
    </div>
  );
}