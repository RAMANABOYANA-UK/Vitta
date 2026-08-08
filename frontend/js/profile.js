// ============ PROFILE PAGE ============

const PROFILE_DRAFT_KEY = 'aviraaProfileDraft';

function getProfileDraft() {
  try {
    return JSON.parse(localStorage.getItem(PROFILE_DRAFT_KEY));
  } catch {
    return null;
  }
}

function saveProfileDraft(profileData) {
  localStorage.setItem(PROFILE_DRAFT_KEY, JSON.stringify(profileData));
}

function clearProfileDraft() {
  localStorage.removeItem(PROFILE_DRAFT_KEY);
}

function applyProfileValues(profileData) {
  if (!profileData) return;

  const setVal = (id, val) => {
    const el = document.getElementById(id);
    if (el && val !== undefined && val !== null) el.value = val;
  };

  setVal('pName', profileData.name);
  setVal('pEmail', profileData.email);
  setVal('pRole', profileData.currentRole);
  setVal('pTargetRole', profileData.targetRole);
  setVal('pExperience', profileData.experience);
  setVal('pAge', profileData.age);
  setVal('pLocations', (profileData.preferences?.locations || []).join(', '));

  const jobTypes = profileData.preferences?.jobTypes || [];
  const jobTypeSelect = document.getElementById('pJobTypes');
  if (jobTypeSelect) {
    Array.from(jobTypeSelect.options).forEach(opt => {
      opt.selected = jobTypes.includes(opt.value);
    });
  }

  const skills = profileData.skills || [];
  const skillsEl = document.getElementById('pSkills');
  if (skillsEl && skills.length > 0) {
    skillsEl.value = skills.map(s => `${s.name} ${s.level}`).join(', ');
  }
}

async function loadProfile() {
  if (!api.requireAuth()) return;

  try {
    let user = await api.get('/auth/profile');
    if (!user) user = {};

    applyProfileValues(user);

    const draft = getProfileDraft();
    if (draft) {
      applyProfileValues({ ...user, ...draft, preferences: { ...(user.preferences || {}), ...(draft.preferences || {}) } });
    }

    // Update avatar and header
    const avatar = document.getElementById('profileAvatar');
    const nameEl = document.getElementById('profileName');
    if (avatar && user.name) avatar.textContent = user.name.charAt(0).toUpperCase();
    if (nameEl && user.name) nameEl.textContent = user.name;

    // Cache
    api.setUser(user);
  } catch (error) {
    console.warn('Profile load failed:', error.message);
    // Fallback to cached user
    const cached = api.getUser();
    if (cached) {
      const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el && val !== undefined && val !== null) el.value = val;
      };
      setVal('pName', cached.name);
      setVal('pEmail', cached.email);
      setVal('pRole', cached.currentRole);
      setVal('pTargetRole', cached.targetRole);
    }

    const draft = getProfileDraft();
    if (draft) {
      applyProfileValues(draft);
    }
  }
}

async function saveProfile(e) {
  e.preventDefault();
  const btn = document.getElementById('saveProfileBtn');
  const successMsg = document.getElementById('profileSuccess');

  const getVal = (id) => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };

  // Parse skills
  const skillsText = getVal('pSkills');
  const skills = skillsText
    .split(',')
    .map(s => s.trim())
    .filter(Boolean)
    .map(s => {
      const match = s.match(/^(.*?)\s*(\d{1,3})$/);
      if (match) {
        return { name: match[1].trim(), level: Math.min(100, parseInt(match[2])) };
      }
      return { name: s, level: 50 };
    });

  // Parse job types
  const jobTypeSelect = document.getElementById('pJobTypes');
  const jobTypes = jobTypeSelect
    ? Array.from(jobTypeSelect.selectedOptions).map(o => o.value)
    : [];

  // Parse locations
  const locations = getVal('pLocations')
    .split(',')
    .map(l => l.trim())
    .filter(Boolean);

  const profileData = {
    name: getVal('pName'),
    email: getVal('pEmail'),
    currentRole: getVal('pRole'),
    targetRole: getVal('pTargetRole'),
    experience: parseInt(getVal('pExperience')) || 0,
    age: parseInt(getVal('pAge')) || undefined,
    skills,
    preferences: { jobTypes, locations }
  };

  try {
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
    saveProfileDraft(profileData);

    // Try API first
    const savedUser = await api.put('/auth/profile', profileData);
    clearProfileDraft();

    // Always cache locally from the server-confirmed payload
    const cached = api.getUser() || {};
    const updated = { ...cached, ...(savedUser || profileData) };
    api.setUser(updated);

// Update avatar
    const avatar = document.getElementById('profileAvatar');
    const nameEl = document.getElementById('profileName');
    if (avatar && profileData.name) avatar.textContent = profileData.name.charAt(0).toUpperCase();
    if (nameEl && profileData.name) nameEl.textContent = profileData.name;

    // Re-render the sidebar completion ring with the updated profile
    if (typeof renderProfileRing === 'function' && typeof computeProfileCompletion === 'function') {
      renderProfileRing(computeProfileCompletion(updated));
    }

    // Dispatch a custom event so other pages (Career AI, etc.) re-render reactively
    window.dispatchEvent(new CustomEvent('aviraa:profile-updated', { detail: updated }));

    // Show success
    successMsg.style.display = 'block';
    successMsg.textContent = 'Profile saved successfully!';
    setTimeout(() => { successMsg.style.display = 'none'; }, 3000);
  } catch (error) {
    console.error('Save failed:', error);
    successMsg.textContent = 'Saved as a local draft. Sync failed, but your edits were kept.';
    successMsg.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-save"></i> Save Profile';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  if (!api.requireAuth()) return;

  loadProfile();

  const form = document.getElementById('profileForm');
  if (form) form.addEventListener('submit', saveProfile);

  form?.addEventListener('input', () => {
    const getVal = (id) => {
      const el = document.getElementById(id);
      return el ? el.value.trim() : '';
    };

    const jobTypeSelect = document.getElementById('pJobTypes');
    const jobTypes = jobTypeSelect
      ? Array.from(jobTypeSelect.selectedOptions).map(o => o.value)
      : [];

    const locations = getVal('pLocations')
      .split(',')
      .map(l => l.trim())
      .filter(Boolean);

    const skillsText = getVal('pSkills');
    const skills = skillsText
      .split(',')
      .map(s => s.trim())
      .filter(Boolean)
      .map(s => {
        const match = s.match(/^(.*?)\s*(\d{1,3})$/);
        if (match) {
          return { name: match[1].trim(), level: Math.min(100, parseInt(match[2])) };
        }
        return { name: s, level: 50 };
      });

    saveProfileDraft({
      name: getVal('pName'),
      email: getVal('pEmail'),
      currentRole: getVal('pRole'),
      targetRole: getVal('pTargetRole'),
      experience: parseInt(getVal('pExperience')) || 0,
      age: parseInt(getVal('pAge')) || undefined,
      skills,
      preferences: { jobTypes, locations }
    });
  });
});

async function triggerTestDigest() {
  try {
    const res = await api.post('/auth/send-digest', {});
    if (typeof showToast === 'function') {
      showToast('📧 Test Digest email triggered successfully!');
    } else {
      alert('📧 Test Digest email triggered successfully!');
    }
  } catch (err) {
    alert('Failed to send test digest: ' + err.message);
  }
}

window.triggerTestDigest = triggerTestDigest;