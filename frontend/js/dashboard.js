// ============ DASHBOARD ============

function updateDateDisplay() {
  const now = new Date();
  const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
  const dateEl = document.getElementById('dateDisplay');
  if (dateEl) dateEl.textContent = now.toLocaleDateString('en-US', options);
}

async function loadDashboardData() {
  try {
    const data = await api.get('/dashboard');

    // Update stat cards
    const statCareer = document.getElementById('statCareer');
    const statWellness = document.getElementById('statWellness');
    const statOpportunities = document.getElementById('statOpportunities');
    const statChats = document.getElementById('statChats');
    const careerBar = document.getElementById('careerProgressBar');

    if (statCareer) statCareer.textContent = `${data.careerProgress || 0}%`;
    if (statWellness) statWellness.textContent = data.wellnessStreak || 0;
    if (statOpportunities) statOpportunities.textContent = data.opportunityCount || 0;
    if (statChats) statChats.textContent = data.recentChats || 0;
    if (careerBar) careerBar.style.width = `${data.careerProgress || 0}%`;

    // AI Insight
    const insightEl = document.getElementById('aiInsightText');
    if (insightEl && data.aiInsight) insightEl.textContent = data.aiInsight;

    // Career Snapshot
    const user = api.getUser() || {};
    const currentRole = document.getElementById('currentRole');
    const targetRole = document.getElementById('targetRole');
    if (currentRole) currentRole.textContent = user.currentRole || data.career?.currentRole || 'Not set';
    if (targetRole) targetRole.textContent = user.targetRole || data.career?.targetRole || 'Not set';

    const skills = data.career?.skills || [];
    if (skills.length > 0) {
      const avg = Math.round(skills.reduce((a, s) => a + s.level, 0) / skills.length);
      const skillsReady = document.getElementById('skillsReady');
      const snapshotBar = document.getElementById('snapshotProgressBar');
      const snapshotSkills = document.getElementById('snapshotSkills');
      if (skillsReady) skillsReady.textContent = `${avg}% (${skills.length} skills)`;
      if (snapshotBar) snapshotBar.style.width = `${avg}%`;
      if (snapshotSkills) {
        snapshotSkills.innerHTML = skills.slice(0, 3).map(s =>
          `<span class="tag tag-rose">${s.name} ${s.level}%</span>`
        ).join('');
      }
    }

    // Wellness snapshot
    const wellness = data.wellness || {};
    const moods = wellness.moods || [];
    if (moods.length > 0) {
      const lastMood = moods[moods.length - 1];
      const moodCircle = document.querySelector('#wellnessSnapshot .metric-circle span');
      if (moodCircle) moodCircle.textContent = lastMood.emoji || '😊';
    }

    // Opportunities top matches
    const topMatches = document.getElementById('topMatches');
    if (topMatches) {
      try {
        const opps = await api.get('/opportunities');
        if (Array.isArray(opps) && opps.length > 0) {
          const top3 = opps.slice(0, 3);
          topMatches.innerHTML = top3.map(o => `
            <div class="match-item" onclick="window.location.href='pages/opportunities.html'">
              <div class="match-score-badge">${o.matchScore || o.mlMatchScore || 0}%</div>
              <div class="match-info">
                <strong>${o.title}</strong>
                <p>${o.company || o.provider || ''}${o.location ? ' · ' + o.location : ''}${o.salary ? ' · ' + o.salary : ''}</p>
              </div>
              <i class="fas fa-chevron-right"></i>
            </div>
          `).join('');
        }
      } catch (e) {
        console.warn('Top matches unavailable:', e.message);
      }
    }

    // Recent activity
    const activityList = document.getElementById('activityList');
    if (activityList) {
      let items = [];
      (data.recentMoods || []).forEach(m => {
        items.push(`
          <div class="activity-item">
            <div class="activity-icon sage"><i class="fas fa-heart"></i></div>
            <div class="activity-info"><p>Mood logged: <strong>${m.emoji || ''} ${m.mood || ''}</strong></p><small>Wellness check-in</small></div>
          </div>
        `);
      });
      (data.recentCareerGoals || []).forEach(g => {
        items.push(`
          <div class="activity-item">
            <div class="activity-icon rose"><i class="fas fa-briefcase"></i></div>
            <div class="activity-info"><p>Career goal: <strong>${g.title}</strong></p><small>Active goal</small></div>
          </div>
        `);
      });
      if (items.length > 0) {
        activityList.innerHTML = items.join('');
      }
    }

  } catch (error) {
    console.error('Failed to load dashboard:', error);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  if (!api.requireAuth()) return;

  updateDateDisplay();
  loadDashboardData();

  console.log('Aviraa Dashboard ready (real-time data)');
});