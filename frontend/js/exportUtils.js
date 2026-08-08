/**
 * Aviraa Progress Report Export Utility
 * Generates styled PDF reports and downloadable CSV spreadsheets.
 */

const exportUtils = {
  /**
   * Generates and downloads a clean, styled PDF progress report
   */
  exportPDFReport(title, user, careerData = {}, wellnessData = {}) {
    const printWindow = window.open('', '_blank', 'width=800,height=900');
    if (!printWindow) {
      alert('Please allow popups to download/print your report.');
      return;
    }

    const name = user?.name || 'Aviraa User';
    const role = user?.currentRole || 'N/A';
    const targetRole = user?.targetRole || 'N/A';
    const skills = user?.skills || [];
    const dateStr = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });

    const htmlContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <title>${title} - ${name}</title>
        <style>
          body { font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; color: #1a1a2e; padding: 40px; background: #fff; line-height: 1.6; }
          .header { text-align: center; border-bottom: 2px solid #b86b7d; padding-bottom: 20px; margin-bottom: 30px; }
          .header h1 { color: #b86b7d; margin: 0; font-size: 26px; }
          .header p { color: #6b5b62; margin: 4px 0 0 0; font-size: 14px; }
          .section { margin-bottom: 30px; background: #fdfaf7; padding: 20px; border-radius: 12px; border: 1px solid #e5d9dd; }
          .section-title { color: #b86b7d; font-size: 18px; margin-top: 0; border-bottom: 1px solid #e5d9dd; padding-bottom: 8px; }
          .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 12px; }
          .stat-box { background: #fff; padding: 14px; border-radius: 8px; border: 1px solid #e5d9dd; }
          .stat-label { font-size: 12px; color: #6b5b62; text-transform: uppercase; font-weight: bold; }
          .stat-value { font-size: 18px; font-weight: bold; color: #1a1a2e; margin-top: 4px; }
          table { width: 100%; border-collapse: collapse; margin-top: 12px; }
          th, td { border: 1px solid #e5d9dd; padding: 10px; text-align: left; font-size: 14px; }
          th { background: #fef3e4; color: #c4855a; }
          .footer { text-align: center; margin-top: 40px; font-size: 12px; color: #6b5b62; border-top: 1px solid #e5d9dd; padding-top: 16px; }
          @media print {
            body { padding: 0; }
            .no-print { display: none; }
          }
        </style>
      </head>
      <body>
        <div class="no-print" style="margin-bottom: 20px; text-align: right;">
          <button onclick="window.print()" style="background:#b86b7d; color:white; padding:10px 20px; border:none; border-radius:8px; cursor:pointer; font-weight:bold;">🖨️ Print / Save as PDF</button>
        </div>

        <div class="header">
          <h1>🌱 Aviraa — ${title}</h1>
          <p>Generated for <strong>${name}</strong> on ${dateStr}</p>
        </div>

        <div class="section">
          <h3 class="section-title">👤 Profile Snapshot</h3>
          <div class="grid">
            <div class="stat-box"><div class="stat-label">Current Role</div><div class="stat-value">${role}</div></div>
            <div class="stat-box"><div class="stat-label">Target Role</div><div class="stat-value">${targetRole}</div></div>
            <div class="stat-box"><div class="stat-label">Experience</div><div class="stat-value">${user?.experience || 0} Years</div></div>
            <div class="stat-box"><div class="stat-label">Total Skills Logged</div><div class="stat-value">${skills.length}</div></div>
          </div>
        </div>

        <div class="section">
          <h3 class="section-title">💼 Career Skills & Proficiency Roadmap</h3>
          ${skills.length > 0 ? `
            <table>
              <thead>
                <tr>
                  <th>Skill Name</th>
                  <th>Proficiency Level</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                ${skills.map(s => `
                  <tr>
                    <td><strong>${s.name}</strong></td>
                    <td>${s.level}%</td>
                    <td>${s.level >= 80 ? '🔥 Advanced' : s.level >= 50 ? '📈 Intermediate' : '🌱 Emerging'}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          ` : '<p style="color:#6b5b62;">No explicit skills recorded yet.</p>'}
        </div>

        <div class="section">
          <h3 class="section-title">🌿 Wellness & Consistency Summary</h3>
          <div class="grid">
            <div class="stat-box"><div class="stat-label">Current Streak</div><div class="stat-value">${wellnessData.streakDays || 1} Days</div></div>
            <div class="stat-box"><div class="stat-label">Latest Mood</div><div class="stat-value">${wellnessData.mood || 'Balanced'}</div></div>
            <div class="stat-box"><div class="stat-label">Water Intake</div><div class="stat-value">${wellnessData.waterGlasses || 6} / 8 Glasses</div></div>
            <div class="stat-box"><div class="stat-label">Sleep Duration</div><div class="stat-value">${wellnessData.sleepHours || 7.5} Hours</div></div>
          </div>
        </div>

        <div class="footer">
          <p>Aviraa 🌱 AI-Powered Growth & Wellness Companion for Women · Confidential Report</p>
        </div>

        <script>
          // Trigger print dialog after content renders
          window.onload = function() {
            setTimeout(function() { window.print(); }, 500);
          }
        </script>
      </body>
      </html>
    `;

    printWindow.document.open();
    printWindow.document.write(htmlContent);
    printWindow.document.close();
  },

  /**
   * Downloads structured CSV data file
   */
  exportCSV(filename, rows) {
    if (!rows || !rows.length) return;
    const separator = ',';
    const keys = Object.keys(rows[0]);
    const csvContent =
      keys.join(separator) +
      '\n' +
      rows.map(row => {
        return keys.map(k => {
          let cell = row[k] === null || row[k] === undefined ? '' : row[k];
          cell = String(cell).replace(/"/g, '""');
          if (cell.search(/("|,|\n)/g) >= 0) {
            cell = `"${cell}"`;
          }
          return cell;
        }).join(separator);
      }).join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }
};

window.exportUtils = exportUtils;
