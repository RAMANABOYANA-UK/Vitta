// ============ CAREER API CONNECTIONS ============

async function loadCareerData() {
  if (!api.requireAuth()) return;
  
  try {
    const [career, profile, dashboard] = await Promise.all([
      api.get('/career'),
      api.get('/auth/profile'),
      api.get('/dashboard')
    ]);
    
    // Update skills
    const skills = career.skills || [];
    if (skills.length > 0) {
      updateSkillsUI(skills);
    }
    
    // Update goals
    if (career.goals) {
      updateGoalsUI(career.goals, profile);
    }
    
    // Update insights
    updateCareerOverview(career, profile, dashboard);
    
  } catch (error) {
    console.error('Failed to load career data:', error);
  }
}

async function saveSkill(skillName, level) {
  try {
    await api.put('/career/skills', { name: skillName, level });
    showToast('✅ Skill updated');
  } catch (error) {
    showToast('❌ Failed to save skill');
  }
}

function updateSkillsUI(skills) {
  const container = document.getElementById('careerSkillsList');
  if (!container) return;
  
  container.innerHTML = skills.map(skill => `
    <div class="skill-item">
      <div class="skill-info">
        <span>${skill.name}</span>
        <span>${skill.level}%</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill rose" style="width:${skill.level}%"></div>
      </div>
    </div>
  `).join('');
}

function updateGoalsUI(goals, profile) {
  const currentRole = (profile?.currentRole || '').trim() || 'Product Specialist / Engineer';
  const targetRole = (profile?.targetRole || '').trim() || 'Senior Tech & Product Leader';
  const lastGoal = goals && goals.length > 0 ? goals[goals.length - 1] : null;

  const prevRoleEl = document.getElementById('careerPreviousRole');
  const prevRoleMeta = document.getElementById('careerPreviousRoleMeta');
  const currentRoleEl = document.getElementById('careerCurrentRole');
  const currentRoleMeta = document.getElementById('careerCurrentRoleMeta');
  const targetRoleEl = document.getElementById('careerTargetRole');
  const targetRoleMeta = document.getElementById('careerTargetRoleMeta');
  const longTermRoleEl = document.getElementById('careerLongTermRole');
  const longTermRoleMeta = document.getElementById('careerLongTermRoleMeta');

  if (prevRoleEl) prevRoleEl.textContent = 'Foundation & Onboarding';
  if (prevRoleMeta) prevRoleMeta.textContent = 'Completed · Skills & Profile Verified';
  if (currentRoleEl) currentRoleEl.textContent = currentRole;
  if (currentRoleMeta) currentRoleMeta.textContent = `Current Role · ${profile?.age ? `Age ${profile.age}` : 'Syncing profile'}`;
  if (targetRoleEl) targetRoleEl.textContent = targetRole;
  if (targetRoleMeta) targetRoleMeta.textContent = lastGoal ? `Target: ${lastGoal.title}` : `Target: ${targetRole}`;
  if (longTermRoleEl) longTermRoleEl.textContent = profile?.preferences?.longTermGoal || 'VP / Executive Growth';
  if (longTermRoleMeta) longTermRoleMeta.textContent = lastGoal?.targetDate ? `Long-term goal · ${new Date(lastGoal.targetDate).getFullYear()}` : 'Long-term goal · based on your profile';
}

function updateCareerOverview(career, profile, dashboard) {
  const progress = dashboard?.careerProgress || Math.round((career.skills || []).reduce((sum, skill) => sum + skill.level, 0) / ((career.skills || []).length || 1));
  const skills = career.skills || [];
  const coursesCount = career.goals ? career.goals.length : 0;

  const progressEl = document.getElementById('careerGoalProgress');
  const progressBar = document.getElementById('careerGoalProgressBar');
  const skillsCountEl = document.getElementById('careerSkillsCount');
  const coursesCountEl = document.getElementById('careerCoursesCount');
  const trackTag = document.getElementById('careerTrackTag');
  const insightPrimary = document.getElementById('careerInsightPrimary');
  const insightSecondary = document.getElementById('careerInsightSecondary');
  const insightTertiary = document.getElementById('careerInsightTertiary');
  const resourcesGrid = document.getElementById('careerResourcesGrid');

  if (progressEl) progressEl.textContent = `${progress}%`;
  if (progressBar) progressBar.style.width = `${progress}%`;
  if (skillsCountEl) skillsCountEl.textContent = String(skills.length);
if (coursesCountEl) coursesCountEl.textContent = String(coursesCount);
  if (trackTag) {
    const role = (profile?.currentRole || '').trim();
    trackTag.textContent = role ? `${role} Track` : 'Your Career Track';
  }

  const topSkill = skills[0];
  const nextSkill = skills[1];
  if (insightPrimary && topSkill) {
    insightPrimary.innerHTML = `<strong>💡 Skill Priority:</strong> Build on ${topSkill.name} next. Your current strength is ${topSkill.level}%.`;
  }
  if (insightSecondary && dashboard?.aiInsight) {
    insightSecondary.innerHTML = `<strong>📊 Market Insight:</strong> ${dashboard.aiInsight}`;
  }
  if (insightTertiary && nextSkill) {
    insightTertiary.innerHTML = `<strong>🎯 Quick Win:</strong> Focus your next project on ${nextSkill.name} to close the gap faster.`;
  }

if (resourcesGrid) {
    const resourceCards = [];
    if (skills[0]) {
      resourceCards.push({ tag: 'Skill Builder', title: `${skills[0].name} Deep Dive`, meta: `Targeting ${skills[0].level}% mastery`, cta: 'Open' });
    }
    if (skills[1]) {
      resourceCards.push({ tag: 'Next Skill', title: `${skills[1].name} Practice Plan`, meta: `Stretch toward ${skills[1].level}%`, cta: 'Open' });
    }
    resourceCards.push({ tag: 'Mentorship', title: 'Leadership Mentorship', meta: 'Matched from your growth goals', cta: 'Apply' });

    resourcesGrid.innerHTML = resourceCards.map(card => `
      <div class="resource-card">
        <span class="tag tag-sage">${card.tag}</span>
        <h4>${card.title}</h4>
        <p>${card.meta}</p>
        <div class="resource-footer">
          <span>Live from your profile</span>
          <button class="btn btn-outline btn-sm">${card.cta}</button>
        </div>
      </div>
    `).join('');
  }

  // Load the personalized learning path from the backend
  loadLearningPath();
}

// Load and render the personalized learning path
async function loadLearningPath() {
  const grid = document.getElementById('careerResourcesGrid');
  if (!grid) return;
  try {
    const result = await api.get('/career/learning-path');
    const steps = result.steps || [];
    if (steps.length === 0) return;
    grid.innerHTML = steps.map(step => `
      <div class="resource-card">
        <span class="tag tag-sage">Priority ${step.priority}</span>
        <h4>${step.skill}</h4>
        <p>Level ${step.currentLevel}% → Target ${step.targetLevel}%</p>
        <div class="resource-links">
          ${step.resources.map((r, ri) => `
            <a href="${r.url}" target="_blank" rel="noopener noreferrer" class="resource-link" onclick="event.stopPropagation();">
              <span class="resource-platform">${r.platform}</span>
              <span class="resource-title">${r.title}</span>
              <span class="resource-duration">${r.duration || ''}</span>
            </a>
          `).join('')}
        </div>
        <div class="resource-footer">
          <span>${step.resources.length} resource${step.resources.length !== 1 ? 's' : ''}</span>
        </div>
      </div>
    `).join('');
  } catch (e) {
    console.error('Failed to load learning path:', e);
  }
}

// Load career data on initialize
document.addEventListener('DOMContentLoaded', () => {
  if (!api.requireAuth()) return;
  loadCareerData();

  // ─── REAL-TIME REACTIVITY ─────────────────────────────────────────────
  // The Career AI page must reflect profile changes instantly across pages
  // and tabs. We listen for several signals and re-fetch career data so the
  // page is always in sync with the user's latest profile.

  // 1. Custom event fired by profile.js after saving (same tab).
  window.addEventListener('aviraa:profile-updated', () => {
    loadCareerData();
  });

  // 2. `storage` event fires on every OTHER tab/page when localStorage
  //    aviraaUser changes (e.g. profile saved on another tab/page).
  window.addEventListener('storage', (e) => {
    if (e.key === 'aviraaUser' || e.key === 'aviraaToken') {
      loadCareerData();
    }
  });

  // 3. When the page becomes visible/focused again (user returns to this tab
  //    after editing their profile on the profile page/tab).
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) loadCareerData();
  });
  window.addEventListener('pageshow', loadCareerData);
  window.addEventListener('focus', loadCareerData);

  // 4. Lightweight polling keeps the page fresh even if nothing else fires.
  setInterval(() => {
    if (!document.hidden) loadCareerData();
  }, 30000);
});
// ============ SKILL PROGRESS ANIMATION ============
function animateProgressBars() {
  const progressBars = document.querySelectorAll('.progress-fill');
  
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const bar = entry.target;
        const targetWidth = bar.style.width;
        bar.style.width = '0%';
        setTimeout(() => {
          bar.style.width = targetWidth;
        }, 100);
        observer.unobserve(bar);
      }
    });
  }, { threshold: 0.3 });

  progressBars.forEach(bar => observer.observe(bar));
}

// ============ RESOURCE ENROLL HANDLER ============
function setupResourceButtons() {
  const enrollButtons = document.querySelectorAll('.resource-card .btn');
  
  enrollButtons.forEach(btn => {
    btn.addEventListener('click', function(e) {
      e.preventDefault();
      const courseName = this.closest('.resource-card').querySelector('h4').textContent;
      
      // Show enrollment confirmation
      showToast(`📚 Enrolled in: ${courseName}`);
      
      // Change button state
      this.textContent = '✓ Enrolled';
      this.style.background = 'var(--sage)';
      this.style.color = 'white';
      this.style.border = 'none';
      this.disabled = true;
    });
  });
}

// ============ TOAST NOTIFICATION ============
function showToast(message) {
  // Remove existing toast
  const existingToast = document.querySelector('.toast');
  if (existingToast) existingToast.remove();

  // Create toast
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    bottom: 32px;
    right: 32px;
    background: var(--dark);
    color: white;
    padding: 14px 24px;
    border-radius: 12px;
    font-size: 0.9rem;
    font-weight: 500;
    z-index: 1000;
    animation: slideIn 0.3s ease, fadeOut 0.3s ease 2.5s forwards;
    box-shadow: 0 8px 24px rgba(0,0,0,0.2);
  `;

  document.body.appendChild(toast);

  // Auto remove
  setTimeout(() => {
    if (toast.parentNode) toast.remove();
  }, 3000);
}

// Add toast animations dynamically
const toastStyles = document.createElement('style');
toastStyles.textContent = `
  @keyframes slideIn {
    from { transform: translateX(100px); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
  }
  @keyframes fadeOut {
    from { opacity: 1; }
    to { opacity: 0; }
  }
`;
document.head.appendChild(toastStyles);

// ============ MODAL HELPERS ============
function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('active');
}

// Close modal when clicking outside the modal box
document.addEventListener('click', function(e) {
  if (e.target.classList && e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('active');
  }
});

// ============ RESUME ANALYSER ============
async function analyzeResume() {
  const resumeText = document.getElementById('resumeText').value.trim();
  const resultsEl = document.getElementById('resumeResults');
  
  if (!resumeText) {
    resultsEl.innerHTML = `<div class="message bot">⚠️ Please paste your resume text first.</div>`;
    return;
  }
  
  resultsEl.innerHTML = `<div class="message bot"><i class="fas fa-spinner fa-spin"></i> Analyzing your resume...</div>`;
  
  try {
    const result = await api.post('/career/analyze-resume', { resumeText });
    const scoreColor = result.score >= 70 ? 'var(--sage)' : (result.score >= 45 ? 'var(--rose)' : '#c4855a');
    
    let skillsHtml = result.skillsFound.length
      ? result.skillsFound.map(s => `<span class="tag tag-sage">${s}</span>`).join(' ')
      : '<em>No in-demand skills detected.</em>';
    
    let suggestionsHtml = result.suggestions.map(s => `<li>${s}</li>`).join('');
    
    resultsEl.innerHTML = `
      <div style="text-align:center; margin-bottom:16px;">
        <div style="font-size:2.5rem; font-weight:700; color:${scoreColor};">${result.score}<span style="font-size:1.2rem;">/100</span></div>
        <div style="color:var(--muted); font-size:0.85rem;">ATS Score · ${result.wordCount} words</div>
      </div>
      <div style="margin-bottom:12px;">
        <strong>🔍 Skills Detected:</strong>
        <div style="margin-top:6px; display:flex; gap:6px; flex-wrap:wrap;">${skillsHtml}</div>
      </div>
      <div style="margin-bottom:12px;">
        <strong>💡 Suggestions to Improve:</strong>
        <ul style="margin:8px 0 0 18px; font-size:0.85rem; color:var(--muted); line-height:1.6;">${suggestionsHtml}</ul>
      </div>
    `;
  } catch (error) {
    resultsEl.innerHTML = `<div class="message bot">❌ Failed to analyze resume. ${error.message || ''}</div>`;
  }
}

// ============ INTERVIEW PREP ============
async function getInterviewQuestion() {
  const role = document.getElementById('interviewRole').value.trim();
  const resultsEl = document.getElementById('interviewResults');
  
  resultsEl.innerHTML = `<div class="message bot"><i class="fas fa-spinner fa-spin"></i> Preparing your question...</div>`;
  
  try {
    const result = await api.post('/career/interview-prep', { role, level: 'mid-level' });
    resultsEl.innerHTML = `
      <div class="message bot" style="margin-bottom:12px;">
        <strong>🎤 Question (${result.index + 1}/${result.total}):</strong><br>
        ${result.question}
      </div>
      <div class="message bot" style="background:var(--sage-light); border-bottom-left-radius:4px;">
        <strong>💡 Tips:</strong> ${result.tips}
      </div>
      <div style="margin-top:12px;">
        <button class="btn btn-outline btn-sm" onclick="revealModelAnswer()"><i class="fas fa-eye"></i> Show Model Answer</button>
      </div>
      <div id="modelAnswer" style="display:none; margin-top:12px;">
        <div class="message bot" style="background:#f3e5f5; border-bottom-left-radius:4px;">
          <strong>✅ Model Answer:</strong> ${result.modelAnswer}
        </div>
      </div>
    `;
  } catch (error) {
    resultsEl.innerHTML = `<div class="message bot">❌ Failed to load question. ${error.message || ''}</div>`;
  }
}

function revealModelAnswer() {
  const el = document.getElementById('modelAnswer');
  if (el) el.style.display = 'block';
}

// ============ EXPORT CAREER PLAN ============
async function exportCareerPlan() {
  showToast('📥 Preparing your career plan...');
  try {
    // Use direct fetch for file download (response is text/plain, not JSON)
    const token = api.getToken();
    const baseUrl = API_BASE_URLS[0];
    const response = await fetch(`${baseUrl}/career/export-plan`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });
    
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.message || 'Export failed');
    }
    
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const date = new Date();
    a.href = url;
    a.download = `aviraa-career-plan-${date.toISOString().split('T')[0]}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('✅ Career plan downloaded!');
  } catch (error) {
    showToast('❌ Failed to export career plan');
  }
}

// ============ GET PERSONALIZED PLAN ============
async function getPersonalizedPlan() {
  const planEl = document.getElementById('personalizedPlan');
  if (!planEl) return;
  planEl.innerHTML = `<div class="message bot"><i class="fas fa-spinner fa-spin"></i> Building your personalized plan...</div>`;
  try {
    const plan = await api.get('/career/insights');
    const gapsHtml = (plan.skillGaps && plan.skillGaps.length)
      ? plan.skillGaps.map(g => `
          <div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px solid var(--border);">
            <span>${g.name}</span>
            <span style="color:var(--muted);">${g.level}% <span style="color:var(--rose);">(gap ${g.gap}%)</span></span>
          </div>`).join('')
      : '<em>Add skills to see your gaps.</em>';

    const stepsHtml = (plan.nextSteps && plan.nextSteps.length)
      ? plan.nextSteps.map((s, i) => `<li style="margin-bottom:6px;">${i + 1}. ${s}</li>`).join('')
      : '<li>No steps yet.</li>';

    const roleAdviceHtml = plan.roleAdvice
      ? `<div class="message bot" style="background:var(--sage-light); margin-top:12px;">
           <strong>🤖 Role Strategy:</strong><br>${plan.roleAdvice.recommendation}
         </div>`
      : '';

    planEl.innerHTML = `
      <div class="message bot">
        <strong>💡 ${plan.summary}</strong>
      </div>
      <div style="margin-top:12px;">
        <strong>🔍 Top Skill Gaps:</strong>
        <div style="margin-top:6px;">${gapsHtml}</div>
      </div>
      <div style="margin-top:12px;">
        <strong>📋 Your Next Steps:</strong>
        <ol style="margin:8px 0 0 18px; font-size:0.85rem; color:var(--muted); line-height:1.6;">${stepsHtml}</ol>
      </div>
      ${roleAdviceHtml}
    `;
  } catch (error) {
    planEl.innerHTML = `<div class="message bot">❌ Failed to build plan. ${error.message || ''}</div>`;
  }
}

// ============ VIEW DETAILED REPORT ============
async function viewDetailedReport() {
  const reportEl = document.getElementById('reportResults');
  if (!reportEl) return;
  reportEl.innerHTML = `<div class="message bot"><i class="fas fa-spinner fa-spin"></i> Generating report...</div>`;
  openModal('reportModal');
  try {
    const plan = await api.get('/career/insights');
    const skills = plan.skillGaps || [];
    const steps = plan.nextSteps || [];

    let skillsHtml = skills.length
      ? skills.map(s => `
          <div style="padding:10px 0; border-bottom:1px solid var(--border);">
            <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
              <strong>${s.name}</strong>
              <span style="color:var(--muted);">${s.level}%</span>
            </div>
            <div class="progress-bar"><div class="progress-fill ${s.level >= 70 ? 'rose' : 'sage'}" style="width:${s.level}%"></div></div>
            <div style="font-size:0.8rem; color:var(--rose); margin-top:4px;">Gap to target: ${s.gap}%</div>
          </div>`).join('')
      : '<p style="color:var(--muted);">No skills added yet. Add skills to generate a detailed gap report.</p>';

    let stepsHtml = steps.length
      ? `<ul style="margin:8px 0 0 18px; font-size:0.85rem; color:var(--muted); line-height:1.7;">${steps.map(s => `<li>${s}</li>`).join('')}</ul>`
      : '<p style="color:var(--muted);">No next steps generated yet.</p>';

    reportEl.innerHTML = `
      <div style="margin-bottom:12px;">
        <strong>👤 Current Role:</strong> ${plan.currentRole || 'Not set'} &nbsp;·&nbsp; <strong>🎯 Target Role:</strong> ${plan.targetRole || 'Not set'}
      </div>
      <div style="margin-bottom:12px;">
        <strong>📊 Skill Gap Breakdown:</strong>
        <div style="margin-top:6px;">${skillsHtml}</div>
      </div>
      <div>
        <strong>🗺️ Personalized Next Steps:</strong>
        ${stepsHtml}
      </div>
    `;
  } catch (error) {
    reportEl.innerHTML = `<div class="message bot">❌ Failed to generate report. ${error.message || ''}</div>`;
  }
}

// ============ MAIN ACTION BUTTONS ============
function setupActionButtons() {
  const resumeBtn = document.getElementById('resumeAnalyzerBtn');
  const interviewBtn = document.getElementById('interviewPrepBtn');
  const exportBtn = document.getElementById('exportPlanBtn');
  const analyzeBtn = document.getElementById('analyzeResumeBtn');
  const questionBtn = document.getElementById('getQuestionBtn');
  const getPlanBtn = document.getElementById('getPlanBtn');
  const viewReportBtn = document.getElementById('viewReportBtn');
  
  if (resumeBtn) resumeBtn.addEventListener('click', () => openModal('resumeModal'));
  if (interviewBtn) interviewBtn.addEventListener('click', () => openModal('interviewModal'));
  if (exportBtn) exportBtn.addEventListener('click', exportCareerPlan);
  if (analyzeBtn) analyzeBtn.addEventListener('click', analyzeResume);
  if (questionBtn) questionBtn.addEventListener('click', getInterviewQuestion);
  if (getPlanBtn) getPlanBtn.addEventListener('click', getPersonalizedPlan);
  if (viewReportBtn) viewReportBtn.addEventListener('click', viewDetailedReport);
  
  // Allow Enter key in interview role input
  const roleInput = document.getElementById('interviewRole');
  if (roleInput) {
    roleInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') getInterviewQuestion();
    });
  }
}

// ============ CARD HOVER EFFECTS ============
function setupCardEffects() {
  const cards = document.querySelectorAll('.resource-card');
  
  cards.forEach(card => {
    card.addEventListener('mouseenter', () => {
      card.style.transform = 'translateY(-2px)';
    });
    card.addEventListener('mouseleave', () => {
      card.style.transform = 'translateY(0)';
    });
  });
}

// ============ INITIALIZE ============
function exportCareerPDF() {
  const user = api.getUser() || {};
  if (typeof exportUtils !== 'undefined') {
    exportUtils.exportPDFReport('Career AI Progress Report', user, currentCareerData, {});
  }
}

function exportCareerCSV() {
  const user = api.getUser() || {};
  const skills = user.skills || [];
  if (!skills.length) {
    alert('No skills logged to export.');
    return;
  }
  const rows = skills.map(s => ({
    'Skill Name': s.name,
    'Proficiency Level (%)': s.level,
    'Category': s.category || 'General'
  }));
  if (typeof exportUtils !== 'undefined') {
    exportUtils.exportCSV('aviraa-career-skills.csv', rows);
  }
}

window.exportCareerPDF = exportCareerPDF;
window.exportCareerCSV = exportCareerCSV;

document.addEventListener('DOMContentLoaded', () => {
  animateProgressBars();
  setupResourceButtons();
  setupActionButtons();
  setupCardEffects();
  
  console.log('🚀 Aviraa Career AI Dashboard ready!');
});