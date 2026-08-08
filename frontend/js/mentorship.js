let allMentors = [];
let currentCategory = 'All';
let selectedMentorId = null;

async function loadMentors() {
  if (!api.requireAuth()) return;
  const grid = document.getElementById('mentorGrid');
  if (!grid) return;

  try {
    const mentors = await api.get('/mentorship');
    allMentors = mentors || [];
    renderMentors();
  } catch (err) {
    grid.innerHTML = `<div style="grid-column:1/-1; text-align:center; color:var(--rose);">Failed to load mentors: ${err.message}</div>`;
  }
}

function renderMentors() {
  const grid = document.getElementById('mentorGrid');
  const searchInput = document.getElementById('mentorSearch');
  const searchTerm = searchInput ? searchInput.value.toLowerCase().trim() : '';

  if (!grid) return;

  let filtered = allMentors.filter(m => {
    const matchCat = currentCategory === 'All' || m.category === currentCategory;
    const matchSearch = !searchTerm ||
      m.name.toLowerCase().includes(searchTerm) ||
      m.title.toLowerCase().includes(searchTerm) ||
      m.company.toLowerCase().includes(searchTerm) ||
      (m.expertise || []).some(e => e.toLowerCase().includes(searchTerm));
    return matchCat && matchSearch;
  });

  if (filtered.length === 0) {
    grid.innerHTML = `<div style="grid-column:1/-1; text-align:center; padding:40px; color:var(--muted);">No mentors found matching your filter criteria.</div>`;
    return;
  }

  grid.innerHTML = filtered.map(m => {
    const matchPct = m.computedMatchScore || m.matchScore || 90;
    return `
      <div class="mentor-card">
        <span class="m-badge">🎯 ${matchPct}% Match</span>
        <div class="mentor-header">
          <div class="m-avatar">${m.name.charAt(0)}</div>
          <div class="m-info">
            <h3>${m.name}</h3>
            <div class="m-title">${m.title}</div>
            <div class="m-company">${m.company}</div>
          </div>
        </div>
        <p class="m-bio">${m.bio}</p>
        <div class="m-tags">
          ${(m.expertise || []).map(e => `<span class="m-tag">${e}</span>`).join('')}
        </div>
        <div class="m-footer">
          <div>
            <div style="font-size:0.85rem; font-weight:600; color:var(--dark);">⭐ ${m.rating} (${m.sessionCount} sessions)</div>
            <div class="m-rate">${m.hourlyRate}</div>
          </div>
          <button class="btn" style="background:var(--rose); color:white; border-radius:10px; padding:8px 14px; border:none; cursor:pointer; font-size:0.85rem;" onclick="openRequestModal('${m._id}', '${m.name}')">
            Request Session
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function filterCategory(cat, btn) {
  currentCategory = cat;
  document.querySelectorAll('.suggestion-chip').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderMentors();
}

function openRequestModal(mentorId, mentorName) {
  selectedMentorId = mentorId;
  const modal = document.getElementById('requestModal');
  const title = document.getElementById('modalMentorName');
  if (title) title.textContent = `Request Session with ${mentorName}`;
  if (modal) modal.classList.add('active');
}

function closeModal() {
  const modal = document.getElementById('requestModal');
  if (modal) modal.classList.remove('active');
}

document.addEventListener('DOMContentLoaded', () => {
  loadMentors();

  const searchInput = document.getElementById('mentorSearch');
  if (searchInput) searchInput.addEventListener('input', renderMentors);

  const form = document.getElementById('requestForm');
  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (!selectedMentorId) return;

      const topic = document.getElementById('reqTopic').value;
      const time = document.getElementById('reqTime').value;
      const note = document.getElementById('reqNote').value;

      try {
        const res = await api.post(`/mentorship/${selectedMentorId}/request`, { topic, preferredTime: time, note });
        alert(res.message || 'Mentorship request submitted!');
        closeModal();
      } catch (err) {
        alert('Failed to request session: ' + err.message);
      }
    });
  }
});

window.filterCategory = filterCategory;
window.openRequestModal = openRequestModal;
window.closeModal = closeModal;
