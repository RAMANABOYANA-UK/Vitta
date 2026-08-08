// ============ OPPORTUNITIES ============

let opportunitiesData = [];
let currentFilter = 'all';
let currentSort = 'match';
let currentView = 'grid';
let savedOpportunities = [];
let displayedCount = 6;
let currentApplicationId = null;

// Load saved opportunities from localStorage
try {
  savedOpportunities = JSON.parse(localStorage.getItem('aviraaSavedOpportunities')) || [];
} catch (e) {
  savedOpportunities = [];
}

// ============ API CONNECTIONS ============
async function loadOpportunities() {
  if (!api.requireAuth()) return;

  try {
    const data = await api.get('/opportunities');
    if (Array.isArray(data) && data.length > 0) {
      opportunitiesData = data;
    }
    filterOpportunities();
  } catch (error) {
    console.error('Failed to load opportunities:', error);
    filterOpportunities();
  }
}

async function saveOpportunityToAPI(id) {
  try {
    await api.post(`/opportunities/${id}/save`);
    return true;
  } catch (error) {
    console.error('Failed to save opportunity:', error);
    return false;
  }
}

async function applyToOpportunity(id) {
  try {
    await api.post(`/opportunities/${id}/apply`);
    return true;
  } catch (error) {
    console.error('Failed to apply:', error);
    return false;
  }
}

// ============ RENDER OPPORTUNITIES ============
function renderOpportunities(data) {
  const grid = document.getElementById('opportunitiesGrid');
  const resultsCount = document.getElementById('resultsCount');
  if (!grid) return;

  const filtered = data.slice(0, displayedCount);

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <i class="fas fa-search" style="font-size:3rem; color:var(--muted);"></i>
        <h3>No opportunities found</h3>
        <p>Try adjusting your filters or search terms.</p>
      </div>
    `;
  } else {
    grid.innerHTML = filtered.map(opp => createOpportunityCard(opp)).join('');
  }

  if (resultsCount) {
    resultsCount.textContent = `Showing ${filtered.length} of ${data.length} opportunities`;
  }

  // Update load more button
  const loadMoreBtn = document.getElementById('loadMoreBtn');
  if (loadMoreBtn) {
    loadMoreBtn.style.display = displayedCount >= data.length ? 'none' : 'inline-flex';
  }

  attachCardListeners();
}

function createOpportunityCard(opp) {
  const isSaved = savedOpportunities.includes(opp.id);
  const typeIcon = getTypeIcon(opp.type);
  const typeLabel = getTypeLabel(opp.type);
  const logo = opp.companyLogo || opp.providerLogo || (opp.company ? String(opp.company).substring(0, 2).toUpperCase() : 'AV');

  return `
    <div class="opportunity-card ${currentView === 'list' ? 'list-view' : ''}" data-id="${opp.id}" data-type="${opp.type}">
      ${opp.isNew ? '<span class="new-badge">New</span>' : ''}

      <div class="opp-header">
        <div class="company-logo">${logo}</div>
        <div class="opp-header-info">
          <span class="opp-type">
            <i class="${typeIcon}"></i> ${typeLabel}
          </span>
          <h3>${opp.title}</h3>
          <p class="company-name">${opp.company || opp.provider || ''}</p>
        </div>
        <button class="save-btn ${isSaved ? 'saved' : ''}" onclick="toggleSave(${opp.id})" title="${isSaved ? 'Unsave' : 'Save'}">
          <i class="${isSaved ? 'fas' : 'far'} fa-bookmark"></i>
        </button>
      </div>

      <div class="opp-details">
        ${opp.location ? `<span><i class="fas fa-map-marker-alt"></i> ${opp.location}</span>` : ''}
        ${opp.salary ? `<span><i class="fas fa-rupee-sign"></i> ${opp.salary}</span>` : ''}
        ${opp.duration ? `<span><i class="fas fa-clock"></i> ${opp.duration}</span>` : ''}
      </div>

      <p class="opp-description">${opp.description || ''}</p>

      <div class="opp-tags">
        ${(opp.tags || []).map(tag => `<span class="tag tag-sage">${tag}</span>`).join('')}
      </div>

      <div class="opp-footer">
        <div class="match-score">
          <div class="score-circle" style="--score:${opp.matchScore || 0}">
            <span>${opp.matchScore || 0}%</span>
          </div>
          <small>Match</small>
        </div>
        <div class="opp-actions">
          <span class="posted-date">${opp.postedDate || 'Recently'}</span>
          <button class="btn btn-primary btn-sm" onclick="openApplyModal(${opp.id})">
            ${opp.type === 'course' ? 'Enroll Now' : opp.type === 'mentorship' ? 'Request Match' : 'Apply Now'}
          </button>
        </div>
      </div>
    </div>
  `;
}

function getTypeIcon(type) {
  const icons = {
    job: 'fas fa-briefcase',
    course: 'fas fa-graduation-cap',
    mentorship: 'fas fa-handshake',
    freelance: 'fas fa-laptop'
  };
  return icons[type] || 'fas fa-star';
}

function getTypeLabel(type) {
  const labels = {
    job: 'Full-Time Role',
    course: 'Upskilling Course',
    mentorship: 'Mentorship Program',
    freelance: 'Freelance Project'
  };
  return labels[type] || 'Opportunity';
}

// ============ FILTER & SORT ============
function setFilter(filter, btn) {
  currentFilter = filter;

  document.querySelectorAll('.filter-chip').forEach(chip => chip.classList.remove('active'));
  if (btn) btn.classList.add('active');

  displayedCount = 6;
  filterOpportunities();
}

function filterOpportunities() {
  const searchInput = document.getElementById('searchInput');
  const sortSelect = document.getElementById('sortSelect');
  const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
  const sortValue = sortSelect ? sortSelect.value : 'match';
  currentSort = sortValue;

  let filtered = [...opportunitiesData];

  // Apply category filter (check both type and category fields)
  if (currentFilter !== 'all') {
    filtered = filtered.filter(opp => (opp.category || opp.type) === currentFilter);
  }

  // Apply search
  if (searchTerm) {
    filtered = filtered.filter(opp =>
      (opp.title || '').toLowerCase().includes(searchTerm) ||
      (opp.company || opp.provider || '').toLowerCase().includes(searchTerm) ||
      (opp.description || '').toLowerCase().includes(searchTerm) ||
      (opp.tags || []).some(tag => tag.toLowerCase().includes(searchTerm))
    );
  }

  // Apply sort
  if (sortValue === 'match') {
    filtered.sort((a, b) => (b.matchScore || 0) - (a.matchScore || 0));
  } else if (sortValue === 'recent') {
    filtered.sort((a, b) => (a.isNew === b.isNew) ? 0 : a.isNew ? -1 : 1);
  } else if (sortValue === 'salary') {
    filtered.sort((a, b) => {
      const getMax = (str) => {
        if (!str) return 0;
        const nums = str.match(/[\d.]+/g);
        return nums ? Math.max(...nums.map(Number)) : 0;
      };
      return getMax(b.salary) - getMax(a.salary);
    });
  }

  renderOpportunities(filtered);
}

function loadMore() {
  displayedCount += 4;
  filterOpportunities();
}

// ============ SAVE / UNSAVE ============
function toggleSave(id) {
  const index = savedOpportunities.indexOf(id);
  if (index > -1) {
    savedOpportunities.splice(index, 1);
    showToast('💾 Removed from saved');
  } else {
    savedOpportunities.push(id);
    showToast('💾 Saved!');
    // Fire-and-forget API save
    saveOpportunityToAPI(id);
  }
  localStorage.setItem('aviraaSavedOpportunities', JSON.stringify(savedOpportunities));
  filterOpportunities();
}

// ============ VIEW TOGGLE ============
function toggleView(view) {
  currentView = view;
  document.querySelectorAll('.view-btn').forEach(btn => btn.classList.remove('active'));
  document.querySelectorAll('.view-btn').forEach(btn => {
    if (btn.textContent.toLowerCase().includes(view)) btn.classList.add('active');
  });
  filterOpportunities();
}

// ============ APPLY MODAL ============
function openApplyModal(id) {
  currentApplicationId = id;
  const opp = opportunitiesData.find(o => o.id === id);
  if (!opp) return;

  const modal = document.getElementById('applyModal');
  const content = document.getElementById('applyModalContent');
  if (!modal || !content) return;

  const titleEl = content.querySelector('h2');
  if (titleEl) titleEl.textContent = `Apply for ${opp.title}`;
  modal.classList.add('active');
}

function closeApplyModal() {
  const modal = document.getElementById('applyModal');
  if (modal) modal.classList.remove('active');
  currentApplicationId = null;
}

async function submitApplication() {
  if (!currentApplicationId) return;

  const opp = opportunitiesData.find(o => o.id === currentApplicationId);
  const btn = document.querySelector('#applyModal .btn-primary');
  const originalText = btn ? btn.textContent : '';

  if (btn) {
    btn.textContent = '⏳ Submitting...';
    btn.disabled = true;
  }

  await applyToOpportunity(currentApplicationId);

  if (btn) {
    btn.textContent = '✓ Submitted!';
    btn.style.background = 'var(--sage)';
  }

  showToast(`🎉 Application sent for ${opp.title}! Good luck!`);

  setTimeout(() => {
    closeApplyModal();
    if (btn) {
      btn.textContent = originalText;
      btn.style.background = 'var(--rose)';
      btn.disabled = false;
    }
  }, 1500);
}

// ============ CARD LISTENERS ============
function attachCardListeners() {
  document.querySelectorAll('.opportunity-card').forEach(card => {
    card.addEventListener('click', function(e) {
      if (e.target.closest('.save-btn') || e.target.closest('.btn')) return;

      const id = parseInt(this.dataset.id);
      const opp = opportunitiesData.find(o => o.id === id);
      if (opp) {
        showToast(`📋 ${opp.title}`);
      }
    });
  });
}

// ============ TOAST ============
function showToast(message) {
  const existingToast = document.querySelector('.toast');
  if (existingToast) existingToast.remove();

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

// ============ INITIALIZE ============
document.addEventListener('DOMContentLoaded', () => {
  if (!api.requireAuth()) return;

  // Load from API, fall back to mock on failure
  loadOpportunities();

  console.log('✨ Aviraa Opportunities ready!');
});

// Expose globally
window.setFilter = setFilter;
window.filterOpportunities = filterOpportunities;
window.toggleSave = toggleSave;
window.toggleView = toggleView;
window.openApplyModal = openApplyModal;
window.closeApplyModal = closeApplyModal;
window.submitApplication = submitApplication;
window.loadMore = loadMore;
window.showToast = showToast;