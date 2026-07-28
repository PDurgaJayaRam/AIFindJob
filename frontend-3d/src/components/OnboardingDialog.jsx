import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { saveUserProfile, fetchMyProfile, uploadResume } from '../lib/api.js';

const ROLE_SUGGESTIONS = [
  'Python Developer', 'Java Developer', 'Frontend Developer', 'Backend Developer',
  'Full Stack Developer', 'React Developer', 'Node.js Developer', 'Data Analyst',
  'Data Scientist', 'Machine Learning Engineer', 'DevOps Engineer', 'Cloud Engineer',
  'Graphic Designer', 'UI/UX Designer', 'Product Designer', 'Mobile Developer',
  'Android Developer', 'iOS Developer', 'Flutter Developer', 'DevSecOps',
];

export default function OnboardingDialog({ onComplete }) {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [profile, setProfile] = useState({
    name: '',
    target_roles: [],
    skills: [],
    experience_level: 'fresher',
    resume_text: '',
  });
  const [roleInput, setRoleInput] = useState('');
  const [skillInput, setSkillInput] = useState('');
  const [resumeFile, setResumeFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [status, setStatus] = useState('');

  useEffect(() => {
    fetchMyProfile().then(data => {
      if (data.has_resume) {
        setProfile(prev => ({
          ...prev,
          skills: data.skills || [],
          experience_level: data.is_fresher ? 'fresher' : 'experienced',
          target_roles: data.target_roles || [],
        }));
        if (data.target_roles?.length > 0) {
          onComplete && onComplete();
        }
      }
    }).catch(() => {});
  }, [onComplete]);

  const handleNext = async () => {
    if (step < 4) {
      setStep(step + 1);
    } else {
      setLoading(true);
      setStatus('Saving your profile...');
      try {
        await saveUserProfile(profile);
        setStatus('✓ Profile saved! Finding your matches...');
        // Refresh profile data in context
        const updatedProfile = await fetchMyProfile();
        // Call onComplete with the updated profile
        onComplete && onComplete(updatedProfile);
      } catch (err) {
        setStatus(`Error: ${err.message}`);
      } finally {
        setLoading(false);
      }
    }
  };

  const addRole = (role) => {
    if (role && !profile.target_roles.includes(role)) {
      setProfile(prev => ({ ...prev, target_roles: [...prev.target_roles, role] }));
    }
    setRoleInput('');
  };

  const addSkill = (skill) => {
    if (skill && !profile.skills.includes(skill)) {
      setProfile(prev => ({ ...prev, skills: [...prev.skills, skill] }));
    }
    setSkillInput('');
  };

  const removeRole = (role) => {
    setProfile(prev => ({ ...prev, target_roles: prev.target_roles.filter(r => r !== role) }));
  };

  const removeSkill = (skill) => {
    setProfile(prev => ({ ...prev, skills: prev.skills.filter(s => s !== skill) }));
  };

  const handleResumeUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setResumeFile(file);
    setParsing(true);
    setStatus('Parsing your resume...');
    try {
      const data = await uploadResume(file);
      setProfile(prev => ({
        ...prev,
        skills: data.skills || prev.skills,
        experience_level: data.is_fresher ? 'fresher' : 'experienced',
        target_roles: data.target_roles || prev.target_roles,
        resume_text: data.text_content || '',
        filename: file.name,
      }));
      setStatus('✓ Resume parsed!');
    } catch (err) {
      setStatus(`Error parsing resume: ${err.message}`);
    } finally {
      setParsing(false);
    }
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
      >
        <motion.div
          initial={{ scale: 0.9, y: 20 }}
          animate={{ scale: 1, y: 0 }}
          exit={{ scale: 0.9, y: 20 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
          className="relative glass rounded-3xl p-8 w-full max-w-2xl max-h-[90vh] overflow-y-auto ease-elastic"
        >
          {/* 3D background elements */}
          <div className="absolute inset-0 -z-10 opacity-30">
            <div className="absolute top-10 right-10 w-40 h-40 bg-gradient-to-r from-nebula to-aqua rounded-full blur-3xl" />
            <div className="absolute bottom-10 left-10 w-32 h-32 bg-aqua/20 rounded-full blur-2xl" />
          </div>

          {/* Progress indicator */}
          <div className="flex justify-center mb-8">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="flex items-center">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center font-semibold transition-all ${
                  i <= step ? 'bg-gradient-to-r from-nebula to-aqua text-ink' : 'bg-white/10 text-gray-400'
                }`}>
                  {i}
                </div>
                {i < 4 && <div className={`w-16 h-1 mx-2 ${i < step ? 'bg-aqua' : 'bg-white/20'}`} />}
              </div>
            ))}
          </div>

          {/* Step content */}
          <AnimatePresence mode="wait">
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
            >
              {step === 1 && (
                <div>
                  <motion.h2
                    initial={{ filter: 'blur(10px)', opacity: 0 }}
                    animate={{ filter: 'blur(0px)', opacity: 1 }}
                    transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                    className="text-3xl font-black text-white mb-2 tracking-tighter blur-reveal"
                  >
                    Welcome to JOB<span className="text-aqua">Finder</span>
                  </motion.h2>
                  <p className="text-gray-300 mb-6 blur-reveal" style={{ animationDelay: '0.1s' }}>Let's set up your profile to find the perfect jobs for you.</p>

                  <div className="space-y-6">
                    {/* Resume Upload - PRIMARY */}
                    <div>
                      <label className="block text-sm font-semibold text-aqua mb-3">
                        📄 Upload Your Resume (Recommended)
                      </label>
                      <div className="relative">
                        <input
                          type="file"
                          accept=".pdf,.docx,.txt"
                          onChange={handleResumeUpload}
                          className="absolute inset-0 opacity-0 cursor-pointer"
                          id="resume-upload-inner"
                        />
                        <label
                          htmlFor="resume-upload-inner"
                          className="flex flex-col items-center justify-center p-8 border-2 border-dashed border-aqua/30 rounded-2xl cursor-pointer hover:border-aqua/50 bg-white/[0.02] transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
                        >
                          <svg className="w-12 h-12 text-aqua mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.9l5.5-5.5a4 4 0 015.66 5.66l-3.5 3.5a1 1 0 01-1.42 0l-1.5-1.5" />
                          </svg>
                          <span className="text-white font-medium">
                            {resumeFile ? resumeFile.name : 'Drop your resume here'}
                          </span>
                          <span className="text-gray-400 text-sm mt-1">
                            PDF, DOCX, or TXT • We'll extract your skills automatically
                          </span>
                        </label>
                      </div>
                      {status && <p className="text-sm text-aqua mt-2 blur-reveal">{status}</p>}
                    </div>

                    <div className="text-center text-gray-400">
                      <span>or fill manually</span>
                    </div>
                  </div>
                </div>
              )}

              {step === 2 && (
                <div>
                  <motion.h2
                    initial={{ filter: 'blur(10px)', opacity: 0 }}
                    animate={{ filter: 'blur(0px)', opacity: 1 }}
                    transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                    className="text-3xl font-black text-white mb-2 tracking-tighter blur-reveal"
                  >
                    Target Job Role
                  </motion.h2>
                  <p className="text-gray-300 mb-6 blur-reveal" style={{ animationDelay: '0.1s' }}>What job roles are you looking for? (Select multiple)</p>

                  <div className="space-y-4">
                    <div>
                      <input
                        type="text"
                        value={roleInput}
                        onChange={e => setRoleInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addRole(roleInput))}
                        placeholder="e.g., Python Developer"
                        className="w-full rounded-lg bg-white/[0.02] border border-white/[0.07] px-4 py-2.5 text-white outline-none focus:border-aqua/50 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
                      />
                      <button
                        onClick={() => addRole(roleInput)}
                        className="mt-2 px-4 py-1.5 bg-aqua/20 text-aqua rounded-lg text-sm hover:bg-aqua/30 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
                      >
                        Add Role
                      </button>
                    </div>

                    <div>
                      <p className="text-gray-400 text-sm mb-2">Quick suggestions:</p>
                      <div className="flex flex-wrap gap-2">
                        {ROLE_SUGGESTIONS.filter(r => !profile.target_roles.includes(r)).map(role => (
                          <button
                            key={role}
                            onClick={() => addRole(role)}
                            className="px-3 py-1.5 bg-white/[0.02] border border-white/[0.07] text-gray-300 rounded-lg text-sm hover:bg-aqua/20 hover:text-aqua ease-elastic"
                          >
                            {role}
                          </button>
                        ))}
                      </div>
                    </div>

                    {profile.target_roles.length > 0 && (
                      <div>
                        <p className="text-aqua text-sm mb-2">Your selected roles:</p>
                        <div className="flex flex-wrap gap-2">
                          {profile.target_roles.map(role => (
                            <span
                              key={role}
                              className="px-3 py-1.5 bg-gradient-to-r from-nebula/30 to-aqua/30 text-white rounded-lg text-sm flex items-center gap-2 ease-elastic"
                            >
                              {role}
                              <button onClick={() => removeRole(role)} className="text-white/60 hover:text-white transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]">
                                ×
                              </button>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {step === 3 && (
                <div>
                  <motion.h2
                    initial={{ filter: 'blur(10px)', opacity: 0 }}
                    animate={{ filter: 'blur(0px)', opacity: 1 }}
                    transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                    className="text-3xl font-black text-white mb-2 tracking-tighter blur-reveal"
                  >
                    Your Skills
                  </motion.h2>
                  <p className="text-gray-300 mb-6 blur-reveal" style={{ animationDelay: '0.1s' }}>What technical skills do you have? (We pre-filled from resume)</p>

                  <div className="space-y-4">
                    <div>
                      <input
                        type="text"
                        value={skillInput}
                        onChange={e => setSkillInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addSkill(skillInput))}
                        placeholder="e.g., Python, React, AWS"
                        className="w-full rounded-lg bg-white/[0.02] border border-white/[0.07] px-4 py-2.5 text-white outline-none focus:border-aqua/50 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
                      />
                      <button
                        onClick={() => addSkill(skillInput)}
                        className="mt-2 px-4 py-1.5 bg-aqua/20 text-aqua rounded-lg text-sm hover:bg-aqua/30 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
                      >
                        Add Skill
                      </button>
                    </div>

                    {profile.skills.length > 0 && (
                      <div>
                        <p className="text-aqua text-sm mb-2">Your skills:</p>
                        <div className="flex flex-wrap gap-2">
                          {profile.skills.map(skill => (
                            <span
                              key={skill}
                              className="px-3 py-1.5 bg-white/[0.02] border border-white/[0.07] text-gray-300 rounded-lg text-sm flex items-center gap-2 ease-elastic"
                            >
                              {skill}
                              <button onClick={() => removeSkill(skill)} className="text-gray-500 hover:text-gray-300 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]">
                                ×
                              </button>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {step === 4 && (
                <div>
                  <motion.h2
                    initial={{ filter: 'blur(10px)', opacity: 0 }}
                    animate={{ filter: 'blur(0px)', opacity: 1 }}
                    transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                    className="text-3xl font-black text-white mb-2 tracking-tighter blur-reveal"
                  >
                    Experience Level
                  </motion.h2>
                  <p className="text-gray-300 mb-6 blur-reveal" style={{ animationDelay: '0.1s' }}>Are you a fresher or experienced professional?</p>

                  <div className="grid grid-cols-2 gap-4">
                    {[
                      { value: 'fresher', label: 'Fresher', desc: '0-2 years experience', icon: '🌱' },
                      { value: 'experienced', label: 'Experienced', desc: '2+ years', icon: '🚀' },
                    ].map(opt => (
                      <button
                        key={opt.value}
                        onClick={() => setProfile(prev => ({ ...prev, experience_level: opt.value }))}
                        className={`p-6 rounded-2xl border-2 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)] ${
                          profile.experience_level === opt.value
                            ? 'border-aqua bg-aqua/10'
                            : 'border-white/[0.07] bg-white/[0.02] hover:border-aqua/30'
                        }`}
                      >
                        <div className="text-3xl mb-2">{opt.icon}</div>
                        <div className="text-xl font-semibold text-white">{opt.label}</div>
                        <div className="text-gray-400 text-sm">{opt.desc}</div>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </motion.div>
          </AnimatePresence>

          {/* Navigation */}
          <div className="flex justify-between mt-8">
            <button
              onClick={() => step > 1 && setStep(step - 1)}
              disabled={step === 1}
              className="px-6 py-2.5 text-gray-400 hover:text-white disabled:opacity-50 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
            >
              Back
            </button>
            <button
              onClick={handleNext}
              disabled={
                loading || parsing ||
                (step === 1 && !resumeFile && profile.target_roles.length === 0) ||
                (step === 2 && profile.target_roles.length === 0) ||
                (step === 4 && profile.target_roles.length === 0)
              }
              className="px-8 py-2.5 bg-gradient-to-r from-nebula to-aqua text-ink font-semibold rounded-full hover:opacity-90 disabled:opacity-50 transition-all duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]"
            >
              {loading || parsing ? status : step === 4 ? 'Find My Jobs!' : 'Continue'}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}