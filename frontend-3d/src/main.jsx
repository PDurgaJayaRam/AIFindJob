import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import './index.css';
import Landing from './pages/Landing.jsx';
import Jobs from './pages/Jobs.jsx';
import Login from './pages/Login.jsx';
import Matches from './pages/Matches.jsx';
import Admin from './pages/Admin.jsx';
import Profile from './pages/Profile.jsx';
import { UserProfileProvider } from './context/UserProfileContext.jsx';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <UserProfileProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/matches" element={<Matches />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/admin" element={<Admin />} />
          <Route path="/login" element={<Login />} />
        </Routes>
      </BrowserRouter>
    </UserProfileProvider>
  </React.StrictMode>
);
