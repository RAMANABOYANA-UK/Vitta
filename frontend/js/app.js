// ============ SHARED APP PROFILE LOADER ============
// Loads the real logged-in user into the sidebar on all app pages

// Compute how complete the user's profile is (0-100).
// Counts name, email, current role, target role, experience, skills, and preferences.
function computeProfileCompletion(user = {}) {
  let filled = 0;
  const total = 7;

  if (user.name && String(user.name).trim()) filled++;
  if (user.email && String(user.email).trim()) filled++;
  if (user.currentRole && String(user.currentRole).trim()) filled++;
  if (user.targetRole && String(user.targetRole).trim()) filled++;
  if (user.experience !== undefined && user.experience !== null && Number(user.experience) > 0) filled++;
  if (Array.isArray(user.skills) && user.skills.length > 0) filled++;
  if (user.preferences && ((user.preferences.locations && user.preferences.locations.length) || (user.preferences.jobTypes && user.preferences.jobTypes.length))) filled++;

  return Math.min(100, Math.round((filled / total) * 100));
}

// Wrap the sidebar avatar in a completion ring and show the percentage badge.
// The avatar element is moved inside a .avatar-wrapper > .avatar-ring structure.
function renderProfileRing(pct) {
  const avatarEl = document.querySelector('.user-card .avatar');
  if (!avatarEl) return;

  // If already wrapped, just update.
  let wrapper = avatarEl.closest('.avatar-wrapper');
  if (!wrapper) {
    wrapper = document.createElement('div');
    wrapper.className = 'avatar-wrapper';

    const ring = document.createElement('div');
    ring.className = 'avatar-ring';

    const pctBadge = document.createElement('span');
    pctBadge.className = 'avatar-pct';

    // Move the avatar inside the ring
    avatarEl.parentNode.insertBefore(wrapper, avatarEl);
    ring.appendChild(avatarEl);
    wrapper.appendChild(ring);
    wrapper.appendChild(pctBadge);
  }

  const ring = wrapper.querySelector('.avatar-ring');
  const pctBadge = wrapper.querySelector('.avatar-pct');
  if (ring) ring.style.setProperty('--pct', pct);
  if (pctBadge) pctBadge.textContent = `${pct}%`;
}

async function loadUserProfile() {
  const token = api.getToken();
  if (!token) return;

  try {
    // Try real profile from API
    let user = await api.get('/auth/profile');

    // Update sidebar user card
    const nameEl = document.querySelector('.user-info .name');
    const avatarEl = document.querySelector('.user-card .avatar');
    const planEl = document.querySelector('.plan');

    if (user) {
      const firstName = (user.name || 'User').split(' ')[0];
      if (nameEl) nameEl.textContent = user.name || 'User';
      if (avatarEl) avatarEl.textContent = (user.name || 'U').charAt(0).toUpperCase();
      if (planEl) planEl.textContent = `✨ ${user.currentRole || 'Aviraa Member'}`;

      // Render the profile completion ring
      renderProfileRing(computeProfileCompletion(user));

      // Store in localStorage for other pages
      api.setUser(user);

      // Update greeting if present
      const greetingEl = document.querySelector('.welcome-section h1');
      if (greetingEl) {
        const hour = new Date().getHours();
        let greeting = 'Good morning';
        if (hour >= 12 && hour < 17) greeting = 'Good afternoon';
        if (hour >= 17) greeting = 'Good evening';
        greetingEl.innerHTML = `${greeting}, ${firstName} <span class="wave">👋</span>`;
      }

      // Update page header subtitle if present
      const pageHeader = document.querySelector('.page-header p');
      if (pageHeader && pageHeader.id === 'pageSubtitle') {
        pageHeader.textContent = user.currentRole
          ? `${user.name}'s ${user.currentRole} journey · Targeting ${user.targetRole || 'growth'}`
          : `Welcome, ${firstName}! Set up your profile to personalize your experience.`;
      }
    }
  } catch (error) {
    // Fallback to cached user
    const cached = api.getUser();
    if (cached) {
      const nameEl = document.querySelector('.user-info .name');
      const avatarEl = document.querySelector('.user-card .avatar');
      if (nameEl) nameEl.textContent = cached.name;
      if (avatarEl) avatarEl.textContent = cached.name.charAt(0).toUpperCase();
      renderProfileRing(computeProfileCompletion(cached));
    }
    console.warn('Profile load failed, using cached:', error.message);
  }
}

function setupLogout() {
  const logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', (e) => {
      e.preventDefault();
      api.removeToken();
      window.location.href = 'index.html';
    });
  }
}

// ============ REAL-TIME PROFILE SYNC (across all pages & tabs) ============
// When the profile is updated on ANY page (or in ANY open tab), the `storage`
// event fires on every other page/tab. We re-load the profile + re-render the
// ring so the sidebar stays in real-time sync without a manual refresh.

// Re-load profile whenever the same/focus changes (e.g. user navigates back to
// this tab after editing profile elsewhere).
function refreshProfileFromStorage() {
  if (!api.isAuthenticated()) return;
  const cached = api.getUser();
  // Optimistically update UI from cache immediately for snappy response.
  if (cached) {
    const nameEl = document.querySelector('.user-info .name');
    const avatarEl = document.querySelector('.user-card .avatar, .sidebar .avatar');
    const planEl = document.querySelector('.plan');
    if (nameEl) nameEl.textContent = cached.name || 'User';
    if (avatarEl) avatarEl.textContent = (cached.name || 'U').charAt(0).toUpperCase();
    if (planEl) planEl.textContent = `✨ ${cached.currentRole || 'Aviraa Member'}`;
    renderProfileRing(computeProfileCompletion(cached));
  }
  // Then fetch authoritative data from the API.
  loadUserProfile();
}

document.addEventListener('DOMContentLoaded', () => {
  if (api.isAuthenticated()) {
    loadUserProfile();
    setupLogout();

    // Cross-tab / cross-page real-time sync: when any tab writes aviraaUser,
    // this page re-syncs instantly.
    window.addEventListener('storage', (e) => {
      if (e.key === 'aviraaUser' || e.key === 'aviraaToken') {
        refreshProfileFromStorage();
      }
    });

    // Refresh when the page becomes visible again (user returns to this tab
    // after editing profile on another page/tab).
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) refreshProfileFromStorage();
    });
    window.addEventListener('pageshow', refreshProfileFromStorage);
    window.addEventListener('focus', refreshProfileFromStorage);

    // Lightweight polling keeps the sidebar fresh even if the profile changes
    // on another device/tab while this page stays open.
    setInterval(() => {
      if (!document.hidden) loadUserProfile();
    }, 30000);
  }
});
