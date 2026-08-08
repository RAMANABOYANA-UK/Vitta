// ============ WELLNESS API CONNECTIONS ============

async function loadWellnessData() {
  if (!api.requireAuth()) return;

  try {
    const [data, profile, dashboard, stats, habits] = await Promise.all([
      api.get('/wellness'),
      api.get('/auth/profile'),
      api.get('/dashboard'),
      api.get('/wellness/stats'),
      api.get('/wellness/habits')
    ]);

    // Update streak
    updateWellnessSummary(data, profile, dashboard);

    // Update mood history
    if (data.moods && data.moods.length > 0) {
      updateMoodHistory(data.moods);
    }

    // Update habits checklist
    renderHabits(habits);

    // Update stress chart + weekly summary from stats
    renderStats(stats);

    // Update water/sleep/exercise quick action labels
    updateQuickActionLabels(stats);

  } catch (error) {
    console.error('Failed to load wellness data:', error);
  }
}

// ============ HABITS CHECKLIST ============
function renderHabits(habitData) {
  const list = document.getElementById('habitList');
  const tag = document.getElementById('habitProgressTag');
  const bar = document.getElementById('habitProgressBar');
  if (!list || !habitData || !habitData.habits) return;

  list.innerHTML = habitData.habits.map(h => {
    const pct = Math.min(100, Math.round((h.progress / h.target) * 100));
    return `
      <div class="habit-item ${h.done ? 'done' : ''}" data-key="${h.key}" style="display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:10px;background:${h.done ? 'var(--sage-light)' : '#faf7f5'};margin-bottom:8px;cursor:pointer;border:1px solid ${h.done ? 'var(--sage)' : 'var(--border)'};">
        <span style="font-size:1.3rem;">${h.icon}</span>
        <div style="flex:1;">
          <div style="font-weight:500;font-size:0.9rem;color:var(--dark);">${h.label} ${h.done ? '✓' : ''}</div>
          <div style="font-size:0.75rem;color:var(--muted);">${h.progress} / ${h.target} done</div>
        </div>
        <div style="width:50px;height:6px;background:#eee;border-radius:3px;overflow:hidden;">
          <div style="height:100%;width:${pct}%;background:var(--sage);"></div>
        </div>
      </div>
    `;
  }).join('');

  if (tag) tag.textContent = `${habitData.done} / ${habitData.total} done`;
  if (bar) bar.style.width = `${habitData.percent || 0}%`;

  // Click handler
  list.querySelectorAll('.habit-item').forEach(item => {
    item.addEventListener('click', async () => {
      const key = item.dataset.key;
      try {
        await api.post('/wellness/habits', { key, value: 1 });
        showToast('✅ Habit logged!');
        const fresh = await api.get('/wellness/habits');
        renderHabits(fresh);
      } catch (e) {
        showToast('❌ Failed to log habit');
      }
    });
  });
}

// ============ WEEKLY STATS / SUMMARY ============
function renderStats(stats) {
  if (!stats) return;

  // Stress chart
  const chart = document.getElementById('stressChart');
  if (chart && stats.last7) {
    chart.innerHTML = stats.last7.map(d => {
      const height = d.stress !== null ? `${d.stress * 10}%` : '0%';
      const isToday = d.date === new Date().toISOString().split('T')[0];
      return `
        <div class="chart-bar">
          <div class="bar-fill ${isToday ? 'active' : ''}" style="height:${height}"></div>
          <span>${d.day}</span>
        </div>
      `;
    }).join('');
  }

  // Stress trend text
  const trendText = document.getElementById('stressTrendText');
  const trendTag = document.getElementById('stressTrendTag');
  if (trendText && stats.stressTrend) {
    if (stats.stressTrend === 'decreasing') {
      trendText.innerHTML = '↓ Stress decreasing — keep it up! 🎉';
      trendText.style.color = 'var(--sage)';
    } else if (stats.stressTrend === 'increasing') {
      trendText.innerHTML = '↑ Stress increasing — try breathing exercises 🌿';
      trendText.style.color = 'var(--rose)';
    } else {
      trendText.textContent = '→ Stress is stable. Keep up your self-care!';
      trendText.style.color = 'var(--muted)';
    }
  }
  if (trendTag) trendTag.textContent = stats.stressTrend === 'decreasing' ? '↓ Decreasing' : stats.stressTrend === 'increasing' ? '↑ Increasing' : 'Stable';

  // Weekly summary
  if (stats.averages) {
    const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
    set('avgSleepValue', stats.averages.sleep || '--');
    set('avgWaterValue', stats.averages.water || '--');
    set('exerciseTotalValue', stats.averages.exerciseMin || '--');
    set('avgStressValue', stats.averages.stress || '--');
  }

  // Mood distribution
  const moodDist = document.getElementById('moodDistribution');
  if (moodDist && stats.moodCounts) {
    const entries = Object.entries(stats.moodCounts);
    if (entries.length > 0) {
      moodDist.innerHTML = '<h4 style="margin-bottom:8px;">Mood Distribution (7 days)</h4>' +
        entries.map(([mood, count]) => `
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
            <span style="width:80px;font-size:0.85rem;">${mood}</span>
            <div style="flex:1;height:8px;background:#eee;border-radius:4px;overflow:hidden;">
              <div style="height:100%;width:${Math.min(100, count * 20)}%;background:var(--rose);"></div>
            </div>
            <span style="font-size:0.8rem;color:var(--muted);">${count}x</span>
          </div>
        `).join('');
    } else {
      moodDist.innerHTML = '<p style="color:var(--muted);font-size:0.85rem;">Log your mood daily to see your weekly distribution.</p>';
    }
  }
}

function updateQuickActionLabels(stats) {
  const last = stats && stats.last7 ? stats.last7[stats.last7.length - 1] : null;
  if (!last) return;

  const waterEl = document.getElementById('waterCount');
  if (waterEl && last.water !== null) waterEl.textContent = `${last.water} / 8 glasses today`;

  const sleepEl = document.getElementById('sleepLog');
  if (sleepEl && last.sleep !== null) sleepEl.textContent = `${last.sleep} hrs last night`;

  const exerciseEl = document.getElementById('exerciseCount');
  if (exerciseEl) exerciseEl.textContent = `${last.exerciseMin || 0} min today`;

  const stressEl = document.getElementById('stressLog');
  if (stressEl && last.stress !== null) stressEl.textContent = `Level ${last.stress} / 10 today`;
}

async function saveMood(mood, emoji) {
  try {
    await api.post('/wellness/mood', { mood, emoji });
    showToast('💜 Mood saved');
  } catch (error) {
    showToast('❌ Failed to save mood');
  }
}

async function saveSleep(hours, quality) {
  try {
    await api.post('/wellness/sleep', { hours, quality });
    showToast('🛌 Sleep logged');
  } catch (error) {
    showToast('❌ Failed to save sleep');
  }
}

async function saveWater(glasses) {
  try {
    await api.post('/wellness/water', { glasses });
    showToast('💧 Water logged');
  } catch (error) {
    showToast('❌ Failed to save water');
  }
}

function updateMoodHistory(moods) {
  const timeline = document.getElementById('moodTimeline');
  if (!timeline) return;

  timeline.innerHTML = moods.slice(-7).map(m => {
    const dayName = new Date(m.date).toLocaleDateString('en-US', { weekday: 'short' });
    return `
      <div class="timeline-item">
        <span class="timeline-mood">${m.emoji}</span>
        <span class="timeline-day">${dayName}</span>
      </div>
    `;
  }).join('');
}

// ============ MOOD TRACKING ============
const moodData = {
  current: null,
  history: []
};

try {
  moodData.history = JSON.parse(localStorage.getItem('aviraaMoodHistory')) || [];
} catch (e) {
  moodData.history = [];
}

const moodResponses = {
  '😊': {
    title: "Wonderful! You're thriving today ✨",
    tip: 'Channel this positive energy into your most important career task. Your confidence is high — perfect for negotiations or presentations.',
    color: 'var(--sage)'
  },
  '🙂': {
    title: 'Feeling good! Steady energy 🌤️',
    tip: 'A great day for balanced productivity. Try the Pomodoro technique: 25 minutes of focused work, 5-minute breaks.',
    color: 'var(--sage)'
  },
  '😐': {
    title: 'Okay is perfectly fine 🌥️',
    tip: 'Neutral days are normal. A short walk or quick stretch could lift your energy. Start with one small win.',
    color: '#c4855a'
  },
  '😔': {
    title: 'I hear you. Be gentle with yourself 💜',
    tip: 'Low-energy days need self-compassion. Try the 5-minute breathing exercise. Reduce your to-do list to just 2 priorities.',
    color: 'var(--rose)'
  },
  '😤': {
    title: "Stress detected. Let's reset together 🌿",
    tip: "Your body is asking for a break. Try the desk stretches and the breathing exercise. Journaling can help process what's triggering this.",
    color: 'var(--rose)'
  }
};

function setMood(mood, saveToHistory) {
  // Update UI
  document.querySelectorAll('.mood-btn').forEach(b => b.classList.remove('selected'));
  const selectedBtn = document.querySelector(`[data-mood="${mood}"]`);
  if (selectedBtn) selectedBtn.classList.add('selected');

  // Update feedback
  const response = moodResponses[mood];
  const moodFeedback = document.getElementById('moodFeedback');
  if (moodFeedback && response) {
    moodFeedback.innerHTML = `
      <div class="mood-response" style="border-left: 4px solid ${response.color}; padding: 12px 16px; background: #fdfaf7; border-radius: 12px;">
        <h4 style="color: ${response.color};">${response.title}</h4>
        <p style="color: var(--muted); font-size: 0.9rem;">${response.tip}</p>
      </div>
    `;
  }

  // Update stat card
  const currentMood = document.getElementById('currentMood');
  if (currentMood) currentMood.textContent = mood;

  // Save to history + API
  if (saveToHistory) {
    const today = new Date().toISOString().split('T')[0];
    moodData.history = moodData.history.filter(h => h.date !== today);
    moodData.history.push({ mood, date: today });
    if (moodData.history.length > 7) moodData.history.shift();
    localStorage.setItem('aviraaMoodHistory', JSON.stringify(moodData.history));
    renderMoodTimeline();

    // Save to backend (fire and forget, don't block UI)
    const moodMap = { '😊': 'Great', '🙂': 'Good', '😐': 'Okay', '😔': 'Low', '😤': 'Stressed' };
    saveMood(moodMap[mood] || mood, mood);
  }
}

function isToday(dateString) {
  return dateString === new Date().toISOString().split('T')[0];
}

function renderMoodTimeline() {
  const timeline = document.getElementById('moodTimeline');
  if (!timeline) return;
  const last7Days = moodData.history.slice(-7);

  timeline.innerHTML = last7Days.map(h => {
    const dayName = new Date(h.date).toLocaleDateString('en-US', { weekday: 'short' });
    return `
      <div class="timeline-item">
        <span class="timeline-mood">${h.mood}</span>
        <span class="timeline-day">${dayName}</span>
      </div>
    `;
  }).join('');

  if (last7Days.length === 0) {
    timeline.innerHTML = '<p style="color:var(--muted); font-size:0.85rem;">No moods logged yet this week.</p>';
  }
}

function updateWellnessSummary(wellness, profile, dashboard) {
  const streakEl = document.getElementById('wellnessStreak');
  const cycleDayLabel = document.getElementById('cycleDayLabel');
  const cyclePhaseLabel = document.getElementById('cyclePhaseLabel');
  const cycleProgressText = document.getElementById('cycleProgressText');
  const cyclePredictionText = document.getElementById('cyclePredictionText');
  const cycleEnergyText = document.getElementById('cycleEnergyText');
  const cycleEnergyNote = document.getElementById('cycleEnergyNote');
  const cycleFocusText = document.getElementById('cycleFocusText');
  const cycleFocusNote = document.getElementById('cycleFocusNote');
  const cycleInsightBox = document.getElementById('cycleInsightBox');

  const cycleData = profile?.cycleData || {};
  const lastPeriodDate = cycleData.lastPeriodDate ? new Date(cycleData.lastPeriodDate) : null;
  const cycleLength = Number(cycleData.cycleLength) || 28;
  const periodLength = Number(cycleData.periodLength) || 5;
  const cyclePhase = dashboard?.cyclePhase || 'unknown';

  if (streakEl) streakEl.textContent = String(wellness.streak || 0);

  if (lastPeriodDate && !Number.isNaN(lastPeriodDate.getTime())) {
    const daysSince = Math.floor((Date.now() - lastPeriodDate.getTime()) / 86400000);
    const dayInCycle = (daysSince % cycleLength) + 1;
    const nextCycleIn = cycleLength - (dayInCycle - 1);
    if (cycleDayLabel) cycleDayLabel.textContent = `Day ${dayInCycle}`;
    if (cyclePhaseLabel) cyclePhaseLabel.textContent = `Cycle Phase · ${cyclePhase.charAt(0).toUpperCase() + cyclePhase.slice(1)}`;
    if (cycleProgressText) cycleProgressText.textContent = `Day ${dayInCycle} of ${cycleLength}`;
    if (cyclePredictionText) cyclePredictionText.textContent = `Next cycle predicted in ${nextCycleIn} days`;
  } else {
    if (cycleDayLabel) cycleDayLabel.textContent = 'Day --';
    if (cyclePhaseLabel) cyclePhaseLabel.textContent = 'Cycle Phase · Not set';
    if (cycleProgressText) cycleProgressText.textContent = 'Add cycle data in Profile';
    if (cyclePredictionText) cyclePredictionText.textContent = 'Cycle prediction unavailable';
  }

  const energyMap = {
    menstrual: { energy: 'Low', note: 'Prioritize rest, reflection, and light tasks.', focus: 'Best for: planning' },
    follicular: { energy: 'Rising', note: 'Great window for starting new work and making bold asks.', focus: 'Best for: launching' },
    ovulation: { energy: 'High', note: 'Communication and confidence are strongest here.', focus: 'Best for: meetings' },
    luteal: { energy: 'Moderate', note: 'Excellent for deep work, reviews, and closing loops.', focus: 'Best for: deep work' },
    unknown: { energy: '--', note: 'Your cycle data will populate these insights.', focus: 'Best for: profile setup' }
  };
  const energy = energyMap[cyclePhase] || energyMap.unknown;
  if (cycleEnergyText) cycleEnergyText.textContent = `Energy Level: ${energy.energy}`;
  if (cycleEnergyNote) cycleEnergyNote.textContent = energy.note;
  if (cycleFocusText) cycleFocusText.textContent = energy.focus;
  if (cycleFocusNote) cycleFocusNote.textContent = 'Based on your live profile data.';

  if (cycleInsightBox) {
    const insightByPhase = {
      menstrual: 'Your current phase favors recovery and planning. Keep the workload lighter and protect your energy.',
      follicular: 'This is a strong phase for interviews, networking, and starting new goals.',
      ovulation: 'Use this window for important conversations and high-visibility work.',
      luteal: 'Focus on finishing, organizing, and strategic solo work right now.',
      unknown: 'Add cycle data in your profile to unlock tailored wellness guidance.'
    };
    cycleInsightBox.innerHTML = `<i class="fas fa-lightbulb" style="color:var(--sage);"></i><p><strong>AI Insight:</strong> ${insightByPhase[cyclePhase] || insightByPhase.unknown}</p>`;
  }
}

function setupMoodSelector() {
  const moodBtns = document.querySelectorAll('.mood-btn');
  const lastMood = moodData.history[moodData.history.length - 1];
  if (lastMood && isToday(lastMood.date)) {
    setMood(lastMood.mood, false);
  }

  moodBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const mood = btn.dataset.mood;
      setMood(mood, true);
    });
  });
}

// ============ WELLNESS ACTIONS ============
let waterCount = 0;
const sleepData = { hours: 7.5, logged: false };

function setupWellnessActions() {
  const actionBtns = document.querySelectorAll('.wellness-action-btn');

  actionBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const action = btn.dataset.action;

      switch(action) {
        case 'breathing':
          openBreathingModal();
          break;
        case 'water':
          logWater(btn);
          break;
        case 'sleep':
          logSleep(btn);
          break;
case 'movement':
          showToast('🚶‍♀️ 10-minute walk started! Step outside or walk indoors.');
          logExercise('Walking', 10);
          break;
        case 'journal':
          openJournalPrompt();
          break;
        case 'stretch':
          showToast('🧘‍♀️ 3-minute desk stretch routine: Neck rolls → Shoulder shrugs → Wrist stretches → Seated twist.');
          logHabit('stretch');
          break;
        case 'exercise':
          logExercisePrompter();
          break;
        case 'stress':
          logStressPrompter();
          break;
      }
    });
  });
}

// ============ EXERCISE & STRESS LOGGING ============
async function saveExercise(type, duration) {
  try {
    await api.post('/wellness/exercise', { type, duration });
    showToast('🏃‍♀️ Exercise logged!');
  } catch (error) {
    showToast('❌ Failed to save exercise');
  }
}

async function logExercise(type, duration) {
  await saveExercise(type, duration);
  // Refresh stats
  try {
    const stats = await api.get('/wellness/stats');
    renderStats(stats);
    updateQuickActionLabels(stats);
  } catch (e) { /* ignore */ }
}

function logExercisePrompter() {
  const types = ['Running', 'Walking', 'Yoga', 'Gym', 'Cycling', 'Dancing', 'Swimming', 'Other'];
  const type = prompt('What type of exercise?', 'Walking');
  if (!type) return;
  const duration = prompt('Duration in minutes?', '30');
  if (!duration || isNaN(duration)) return;
  const durationNum = parseFloat(duration);
  logExercise(type, durationNum);
}

async function saveStress(level, triggers) {
  try {
    await api.post('/wellness/stress', { level, triggers });
    showToast('📊 Stress logged');
  } catch (error) {
    showToast('❌ Failed to save stress');
  }
}

function logStressPrompter() {
  const level = prompt('Rate your stress level from 1 (relaxed) to 10 (very stressed):', '5');
  if (!level || isNaN(level)) return;
  const levelNum = Math.min(10, Math.max(1, parseInt(level)));
  const triggers = prompt('What is causing the stress? (comma separated, optional)', '');
  const triggerList = triggers ? triggers.split(',').map(t => t.trim()).filter(Boolean) : [];
  saveStress(levelNum, triggerList).then(async () => {
    try {
      const stats = await api.get('/wellness/stats');
      renderStats(stats);
      updateQuickActionLabels(stats);
    } catch (e) { /* ignore */ }
  });
}

async function logHabit(key) {
  try {
    await api.post('/wellness/habits', { key, value: 1 });
    const fresh = await api.get('/wellness/habits');
    renderHabits(fresh);
  } catch (e) {
    showToast('❌ Failed to log habit');
  }
}

function logWater(btn) {
  waterCount++;
  if (waterCount > 8) waterCount = 8;
  const countEl = document.getElementById('waterCount');
  if (countEl) countEl.textContent = `${waterCount} / 8 glasses today`;

  if (waterCount >= 8) {
    if (btn) {
      btn.style.background = 'var(--sage-light)';
      btn.style.borderColor = 'var(--sage)';
    }
    showToast('💧 Hydration goal achieved! Excellent! 🎉');
  } else {
    showToast(`💧 ${8 - waterCount} more glasses to go!`);
  }

  // Save to backend
  saveWater(waterCount);
}

function logSleep(btn) {
  const hours = prompt('How many hours did you sleep last night?', sleepData.hours);
  if (hours && !isNaN(hours)) {
    sleepData.hours = parseFloat(hours);
    sleepData.logged = true;
    const sleepLog = document.getElementById('sleepLog');
    if (sleepLog) sleepLog.textContent = `${sleepData.hours} hrs last night`;
    showToast(`🛌 ${sleepData.hours} hours logged. ${sleepData.hours >= 7 ? 'Great sleep!' : 'Try to get more rest tonight.'}`);
    saveSleep(sleepData.hours, sleepData.hours >= 7 ? 5 : 3);
  }
}

function openJournalPrompt() {
  const prompts = [
    "What are 3 things you're grateful for today?",
    'What was one small win you had this week?',
    'What boundary do you need to set to protect your energy?',
    'How did you take care of yourself today?'
  ];
  const prompt = prompts[Math.floor(Math.random() * prompts.length)];

  const journalText = prompt(`📝 Journal Prompt:\n\n${prompt}\n\n(Type your thoughts below)`);
  if (journalText) {
    showToast('📝 Journal entry saved! Reflection is powerful.');
  }
}

// ============ BREATHING EXERCISE ============
let breathingInterval;
let breathingSeconds = 300; // 5 minutes
let isBreathing = false;

function openBreathingModal() {
  const modal = document.getElementById('breathingModal');
  if (modal) modal.classList.add('active');
  resetBreathing();
}

function closeBreathingModal() {
  clearInterval(breathingInterval);
  isBreathing = false;
  const modal = document.getElementById('breathingModal');
  if (modal) modal.classList.remove('active');
  resetBreathing();
}

function resetBreathing() {
  breathingSeconds = 300;
  isBreathing = false;
  const timer = document.getElementById('breathingTimer');
  const text = document.getElementById('breathingText');
  const startBtn = document.getElementById('startBreathing');
  const circle = document.getElementById('breathingCircle');
  if (timer) timer.textContent = '5:00';
  if (text) text.textContent = 'Breathe In';
  if (startBtn) startBtn.textContent = 'Start';
  if (circle) circle.classList.remove('animating');
}

function startBreathing() {
  if (isBreathing) return;
  isBreathing = true;

  const btn = document.getElementById('startBreathing');
  const text = document.getElementById('breathingText');
  const timer = document.getElementById('breathingTimer');
  const circle = document.getElementById('breathingCircle');
  if (!btn || !circle) return;

  btn.textContent = 'Running...';
  btn.disabled = true;
  circle.classList.add('animating');

  const phases = ['Breathe In', 'Hold', 'Breathe Out', 'Hold'];
  let phaseIndex = 0;
  const phaseDurations = [4000, 7000, 8000, 1000];

  function runPhase() {
    if (!isBreathing) return;
    if (text) text.textContent = phases[phaseIndex];

    if (phaseIndex === 0) {
      circle.style.transform = 'scale(1.3)';
    } else if (phaseIndex === 2) {
      circle.style.transform = 'scale(1)';
    }

    phaseIndex = (phaseIndex + 1) % 4;
    if (isBreathing) setTimeout(runPhase, phaseDurations[phaseIndex]);
  }

  runPhase();

  // Countdown timer
  breathingInterval = setInterval(() => {
    breathingSeconds--;
    const mins = Math.floor(breathingSeconds / 60);
    const secs = breathingSeconds % 60;
    if (timer) timer.textContent = `${mins}:${secs.toString().padStart(2, '0')}`;

    if (breathingSeconds <= 0) {
      clearInterval(breathingInterval);
      isBreathing = false;
      if (timer) timer.textContent = 'Done! 🎉';
      if (text) text.textContent = 'Great job!';
      circle.classList.remove('animating');
      circle.style.transform = 'scale(1)';
      btn.textContent = 'Done!';
      showToast('🧘 Breathing exercise complete! You did amazing.');

      setTimeout(closeBreathingModal, 2000);
    }
  }, 1000);
}

// ============ TOAST NOTIFICATION ============
function showToast(message) {
  const existingToast = document.querySelector('.toast');
  if (existingToast) existingToast.remove();

  // Add toast styles if not already present
  if (!document.querySelector('#toast-styles')) {
    const toastStyles = document.createElement('style');
    toastStyles.id = 'toast-styles';
    toastStyles.textContent = `
      .toast {
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
        animation: slideInToast 0.3s ease, fadeOutToast 0.3s ease 2.5s forwards;
        box-shadow: 0 8px 24px rgba(0,0,0,0.2);
      }
      @keyframes slideInToast {
        from { transform: translateX(100px); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
      }
      @keyframes fadeOutToast {
        from { opacity: 1; }
        to { opacity: 0; }
      }
    `;
    document.head.appendChild(toastStyles);
  }

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => {
    if (toast.parentNode) toast.remove();
  }, 3000);
}

// ============ STRESS CHART ANIMATION ============
function animateStressChart() {
  const bars = document.querySelectorAll('.bar-fill');
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.transition = 'height 1s ease';
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.5 });

  bars.forEach(bar => observer.observe(bar));
}

// ============ INITIALIZE ============
document.addEventListener('DOMContentLoaded', () => {
  if (!api.requireAuth()) return;

  setupMoodSelector();
  setupWellnessActions();
  renderMoodTimeline();
  animateStressChart();
  loadWellnessData();

  console.log('🌿 Aviraa Wellness Tracker ready!');
});

function exportWellnessPDF() {
  const user = api.getUser() || {};
  if (typeof exportUtils !== 'undefined') {
    exportUtils.exportPDFReport('Preventive Wellness Report', user, {}, wellnessState);
  }
}

function exportWellnessCSV() {
  const logs = wellnessState.moodLogs || [];
  const rows = logs.length > 0 ? logs.map(l => ({
    'Date': new Date(l.createdAt || Date.now()).toLocaleDateString(),
    'Mood': l.mood,
    'Stress Level': l.stressLevel || 'Moderate',
    'Note': l.note || ''
  })) : [
    { 'Date': new Date().toLocaleDateString(), 'Mood': wellnessState.mood || 'Balanced', 'Streak Days': wellnessState.streakDays || 1 }
  ];

  if (typeof exportUtils !== 'undefined') {
    exportUtils.exportCSV('aviraa-wellness-moods.csv', rows);
  }
}

// Expose for inline handlers
window.setMood = setMood;
window.closeBreathingModal = closeBreathingModal;
window.startBreathing = startBreathing;
window.showToast = showToast;
window.exportWellnessPDF = exportWellnessPDF;
window.exportWellnessCSV = exportWellnessCSV;