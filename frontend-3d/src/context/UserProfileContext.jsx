import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import { fetchMyProfile, getToken, setToken } from '../lib/api.js';

const UserProfileContext = createContext(null);

export function useUserProfile() {
  const ctx = useContext(UserProfileContext);
  if (!ctx) throw new Error('useUserProfile must be used within UserProfileProvider');
  return ctx;
}

export function UserProfileProvider({ children }) {
  const [profile, setProfile] = useState(null);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);
  const [loading, setLoading] = useState(true);
  const justCompletedOnboarding = useRef(false);

  // Re-run effect when token changes (detects login)
  const token = getToken();

  useEffect(() => {
    // Skip fetch if we just completed onboarding (profile already set)
    if (justCompletedOnboarding.current) {
      justCompletedOnboarding.current = false;
      return;
    }

    // Check if user has profile - only if they have a token
    
    // No token means no user - clear profile and require login
    if (!token) {
      setProfile(null);
      setNeedsOnboarding(false);
      setLoading(false);
      return;
    }
    
    // Try to fetch profile with valid token
    fetchMyProfile()
      .then(data => {
        if (data.has_resume && data.target_roles?.length > 0) {
          setProfile(data);
          setNeedsOnboarding(false);
        } else if (data.has_resume && !data.target_roles?.length) {
          // Has resume but no target roles - still need to complete onboarding
          setNeedsOnboarding(true);
        } else {
          // No resume - need onboarding
          setNeedsOnboarding(true);
        }
      })
      .catch((err) => {
        // 401 means not authenticated - clear profile
        if (err.message?.includes('401')) {
          setToken(null); // Clear invalid token
          setProfile(null);
          setNeedsOnboarding(false);
        } else {
          // Other error - need onboarding
          setNeedsOnboarding(true);
        }
      })
      .finally(() => setLoading(false));
  }, [token]); // Re-run when token changes (after login)

  const updateProfile = (newData) => {
    setProfile(prev => ({ ...prev, ...newData }));
  };

  const completeOnboarding = (profileData) => {
    justCompletedOnboarding.current = true;
    setProfile(profileData);
    setNeedsOnboarding(false);
  };

  const handleLogout = () => {
    setToken(null); // Clear token
    setProfile(null);
    setNeedsOnboarding(false);
  };

  return (
    <UserProfileContext.Provider value={{ profile, setProfile, needsOnboarding, setNeedsOnboarding, loading, updateProfile, completeOnboarding, handleLogout }}>
      {children}
    </UserProfileContext.Provider>
  );
}