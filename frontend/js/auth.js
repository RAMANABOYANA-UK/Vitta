// ============ LOGIN HANDLER ============
document.addEventListener('DOMContentLoaded', () => {
  const loginForm = document.getElementById('loginForm');
  const signupForm = document.getElementById('signupForm');
  const nextPath = new URLSearchParams(window.location.search).get('next') || 'app.html';

  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      const email = document.getElementById('email').value;
      const password = document.getElementById('password').value;
      const errorDiv = document.getElementById('authError');
      const submitBtn = loginForm.querySelector('button[type="submit"]');

      try {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Logging in...';
        errorDiv.style.display = 'none';

        const data = await api.post('/auth/login', { email, password });
        
        api.setToken(data.token);
        api.setUser(data.user);
        
        window.location.href = nextPath;
      } catch (error) {
        errorDiv.textContent = error.message;
        errorDiv.style.display = 'block';
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Login';
      }
    });
  }

  if (signupForm) {
    signupForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      const name = document.getElementById('name').value;
      const email = document.getElementById('email').value;
      const password = document.getElementById('password').value;
      const confirmPassword = document.getElementById('confirmPassword').value;
      const errorDiv = document.getElementById('authError');
      const submitBtn = signupForm.querySelector('button[type="submit"]');

      // Validate passwords match
      if (password !== confirmPassword) {
        errorDiv.textContent = 'Passwords do not match';
        errorDiv.style.display = 'block';
        return;
      }

      try {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Creating account...';
        errorDiv.style.display = 'none';

        const data = await api.post('/auth/signup', { name, email, password });
        
        api.setToken(data.token);
        api.setUser(data.user);
        
        window.location.href = nextPath;
      } catch (error) {
        errorDiv.textContent = error.message;
        errorDiv.style.display = 'block';
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Create Account';
      }
    });
  }

  // Toggle password visibility
  document.querySelectorAll('.toggle-password').forEach(btn => {
    btn.addEventListener('click', function() {
      const input = this.parentElement.querySelector('input');
      const icon = this.querySelector('i');
      
      if (input.type === 'password') {
        input.type = 'text';
        icon.classList.replace('fa-eye', 'fa-eye-slash');
      } else {
        input.type = 'password';
        icon.classList.replace('fa-eye-slash', 'fa-eye');
      }
    });
  });
});

// Logout function
function logout() {
  api.removeToken();
  const isSubFolder = window.location.pathname.includes('/pages/');
  window.location.href = isSubFolder ? '../index.html' : 'index.html';
}