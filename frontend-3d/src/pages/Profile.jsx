import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { fetchMyPreferences, updateMyPreferences, getToken } from '../lib/api.js';

// Mirrors `profile/router.py:derive_level`. Keep in sync — the backend is
// the source of truth, but we need this client-side so the dropdown reflects
// the user's current level before the form is dirty.
function deriveLevel(years) {
  if (years <= 0) return 'fresher';
  if (years <= 2) return 'junior';
  if (years <= 5) return 'mid';
  return 'senior';
}

function parseList(s) {
  return (s || '').split(',').map(x => x.trim()).filter(Boolean);
}

function joinList(arr) {
  return Array.isArray(arr) ? arr.join(', ') : '';
}

const EMPTY = {
  desired_roles: [],
  desired_locations: [],
  remote_ok: false,
  min_salary: null,
  experience_years: 0,
  skills: [],
  experience_level: 'fresher',
};

export default function Profile() {
  const navigate = useNavigate();
  const [form, setForm] = useState(EMPTY);
  const [rolesText, setRolesText] = useState('');
  const [locationsText, setLocationsText] = useState('');
  const [skillsText, setSkillsText] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState(null);
  const [error, setError] = useState('');
  const [enqueued, setEnqueued] = useState(null);

  // Auth + initial fetch. Per project memory, auth-required fetches must
  // gate on the token so we don't 401-spam the console before login.
  useEffect(() => {
    const token = getToken();
    if (!token) {
      navigate('/login');
      return;
    }
    let active = true;
    fetchMyPreferences()
      .then((data) => {
        if (!active) return;
        const merged = { ...EMPTY, ...data };
        setForm(merged);
        setRolesText(joinList(data.desired_roles));
        setLocationsText(joinList(data.desired_locations));
        setSkillsText(joinList(data.skills));
        setLoading(false);
      })
      .catch((e) => {
        if (!active) return;
        setError(e.message || 'Failed to load profile');
        setLoading(false);
      });
    return () => { active = false; };
  }, [navigate]);

  // Keep experience_level in sync with years whenever years changes.
  useEffect(() => {
    setForm((f) => ({ ...f, experience_level: deriveLevel(f.experience_years) }));
  }, [form.experience_years]);

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setEnqueued(null);
    const payload = {
      desired_roles: parseList(rolesText),
      desired_locations: parseList(locationsText),
      remote_ok: form.remote_ok,
      min_salary: form.min_salary,
      experience_years: form.experience_years,
      skills: parseList(skillsText),
    };
    if (payload.desired_roles.length === 0) {
      setError('Add at least one desired role');
      setSaving(false);
      return;
    }
    if (payload.desired_locations.length === 0) {
      setError('Add at least one desired location');
      setSaving(false);
      return;
    }
    try {
      const result = await updateMyPreferences(payload);
      setForm((f) => ({ ...f, ...result }));
      setSavedAt(new Date());
      // The backend doesn't currently return the enqueue status. Keep
      // the UI honest: we trigger a scrape as a side effect of the PUT,
      // but if the broker is down the user should not see a misleading
      // "queued" badge. Show the derived level for confirmation.
      setEnqueued({ ok: true, level: result.experience_level });
    } catch (e) {
      setError(e.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-300">
        Loading profile...
      </div>
    );
  }

  return (
    <div className="min-h-screen p-6 md:p-12 text-slate-100">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="max-w-3xl mx-auto"
      >
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-4xl font-bold tracking-tight">Your Profile</h1>
            <p className="text-slate-400 mt-2">
              We use this to find fresher and junior roles. Save to refresh your matches.
            </p>
          </div>
          <Link
            to="/jobs"
            className="text-sm text-amber-300 hover:text-amber-200 transition"
          >
            ← Back to jobs
          </Link>
        </div>

        <form
          onSubmit={handleSave}
          className="bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-6 md:p-8 space-y-6"
        >
          <Field
            label="Desired roles"
            hint="Comma-separated. The first one is what we'll search for. e.g. Data Analyst, Junior Software Engineer"
          >
            <input
              type="text"
              value={rolesText}
              onChange={(e) => setRolesText(e.target.value)}
              placeholder="Data Analyst, Junior Python Developer"
              className={inputCls}
            />
          </Field>

          <Field
            label="Desired locations"
            hint="Comma-separated cities. The first one is what we'll search for."
          >
            <input
              type="text"
              value={locationsText}
              onChange={(e) => setLocationsText(e.target.value)}
              placeholder="Hyderabad, Bangalore, Remote"
              className={inputCls}
            />
          </Field>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field label="Experience (years)">
              <input
                type="number"
                min="0"
                max="30"
                step="0.5"
                value={form.experience_years}
                onChange={(e) =>
                  setForm({ ...form, experience_years: Number(e.target.value) || 0 })
                }
                className={inputCls}
              />
            </Field>
            <Field
              label="Derived level"
              hint="Auto-computed. Freshers and juniors get fresher-aware search."
            >
              <input
                type="text"
                value={form.experience_level}
                disabled
                className={inputCls + ' opacity-70 cursor-not-allowed'}
              />
            </Field>
          </div>

          <Field
            label="Skills"
            hint="Comma-separated. e.g. Python, SQL, Excel, React"
          >
            <input
              type="text"
              value={skillsText}
              onChange={(e) => setSkillsText(e.target.value)}
              placeholder="Python, SQL, Excel"
              className={inputCls}
            />
          </Field>

          <Field label="Minimum salary (₹/year, optional)">
            <input
              type="number"
              min="0"
              value={form.min_salary ?? ''}
              onChange={(e) =>
                setForm({
                  ...form,
                  min_salary: e.target.value === '' ? null : Number(e.target.value),
                })
              }
              placeholder="300000"
              className={inputCls}
            />
          </Field>

          <label className="flex items-center gap-3 text-sm text-slate-200">
            <input
              type="checkbox"
              checked={form.remote_ok}
              onChange={(e) => setForm({ ...form, remote_ok: e.target.checked })}
              className="w-4 h-4 rounded border-white/20 bg-white/5"
            />
            Remote roles are fine
          </label>

          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/30 text-red-200 px-4 py-3 text-sm">
              {error}
            </div>
          )}

          {enqueued && (
            <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-200 px-4 py-3 text-sm">
              Saved. We'll re-run the search for <strong>{form.experience_level}</strong> roles.
            </div>
          )}

          <div className="flex items-center justify-between pt-2">
            <div className="text-xs text-slate-500">
              {savedAt ? `Last saved at ${savedAt.toLocaleTimeString()}` : 'Not yet saved'}
            </div>
            <button
              type="submit"
              disabled={saving}
              className="px-5 py-2.5 rounded-xl bg-amber-400 text-slate-900 font-semibold hover:bg-amber-300 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? 'Saving…' : 'Save & refresh jobs'}
            </button>
          </div>
        </form>
      </motion.div>
    </div>
  );
}

const inputCls =
  'w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10 text-slate-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-400/50 focus:border-amber-400/50';

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-200 mb-1">
        {label}
      </label>
      {children}
      {hint && <p className="text-xs text-slate-500 mt-1">{hint}</p>}
    </div>
  );
}
