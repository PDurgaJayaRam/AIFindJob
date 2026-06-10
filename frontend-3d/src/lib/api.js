// Thin API client for the FastAPI backend.
// In dev, Vite proxies these paths to http://localhost:8000 (see vite.config.js).

const TOKEN_KEY = 'jobfinder_token';

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  // Only add Content-Type for JSON requests
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    if (res.status === 401) {
      setToken(null);
    }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json();
}

export function fetchPoolJobs({ limit = 30, offset = 0, source } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (source) params.set('source', source);
  return request(`/ingestion/jobs?${params.toString()}`);
}

export function fetchIngestionStatus() {
  return request('/ingestion/status');
}

export function login(email, password) {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

export function register(email, password, full_name = '') {
  return request('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, full_name }),
  });
}

export function logout() {
  const token = getToken();
  // Clear token from local storage
  setToken(null);
  // Call backend endpoint if we have a token
  if (token) {
    return request('/auth/logout', {
      method: 'POST',
    });
  }
  return Promise.resolve({ message: 'Logged out' });
}

export function fetchMyMatches({ limit = 30, minScore = 0 } = {}) {
  const params = new URLSearchParams({ limit: String(limit), min_score: String(minScore) });
  return request(`/me/matches?${params.toString()}`).then(data => {
    // Handle both old format (error in body) and new format
    if (data?.error?.includes('No resume')) {
      throw new Error(`404 ${data.error}`);
    }
    return data;
  });
}

// Alias for compatibility
export const fetchMatches = fetchMyMatches;

export function fetchMyProfile() {
  return request('/me/profile');
}

export function uploadResume(file) {
  const form = new FormData();
  form.append('file', file);
  const token = getToken();
  const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
  return fetch('/resume/parse', {
    method: 'POST',
    body: form,
    headers,
  }).then(async res => {
    if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
    return res.json();
  });
}

export function saveUserProfile(profile) {
  return request('/me/resume', {
    method: 'POST',
    body: JSON.stringify({
      text_content: profile.resume_text || '',
      skills: profile.skills || [],
      experience_years: profile.experience_level === 'fresher' ? 0 : 2,
      is_fresher: profile.experience_level === 'fresher',
      target_roles: profile.target_roles || [],
      filename: profile.filename || 'resume.txt',
    }),
  });
}

export function generateResume(jobId) {
  return request(`/me/jobs/${jobId}/resume`, { method: 'POST' });
}

export function findContacts(jobId, domain = '', candidateNames = []) {
  return request(`/me/jobs/${jobId}/contacts`, {
    method: 'POST',
    body: JSON.stringify({ domain, candidate_names: candidateNames }),
  });
}

export function draftOutreach(jobId, contactName, channel = 'email') {
  return request('/me/contacts/draft', {
    method: 'POST',
    body: JSON.stringify({ job_id: jobId, contact_name: contactName, channel }),
  });
}

export function fetchAdminOverview() {
  return request('/admin/overview');
}

export function fetchLiveScraperStatus() {
  return request('/live-scraper/status');
}

export function startLiveScraper() {
  return request('/live-scraper/start', { method: 'POST' });
}

export function stopLiveScraper() {
  return request('/live-scraper/stop', { method: 'POST' });
}

export function runLiveScraperDemo() {
  return request('/live-scraper/demo', { method: 'POST' });
}

export function seedDemoJobs() {
  return request('/live-scraper/seed-demo-jobs', { method: 'POST' });
}
