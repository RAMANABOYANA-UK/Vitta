let nodemailer = null;
try {
  nodemailer = require('nodemailer');
} catch (e) {
  console.log('ℹ️ nodemailer module not found, using email logger fallback.');
}

/**
 * Creates a transport if SMTP env vars exist, else logs to console.
 */
function getTransporter() {
  if (nodemailer && process.env.SMTP_HOST) {
    return nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port: process.env.SMTP_PORT || 587,
      secure: process.env.SMTP_SECURE === 'true',
      auth: {
        user: process.env.SMTP_USER,
        pass: process.env.SMTP_PASS
      }
    });
  }
  return null;
}

/**
 * Sends welcome email to new users
 */
async function sendWelcomeEmail(user) {
  const subject = '🌱 Welcome to Aviraa — Your AI Growth & Wellness Companion!';
  const html = `
    <div style="font-family: 'Helvetica Neue', Arial, sans-serif; background:#fdfaf7; padding:30px; color:#1a1a2e;">
      <div style="max-width:550px; margin:0 auto; background:white; border-radius:16px; padding:30px; box-shadow:0 8px 24px rgba(0,0,0,0.05); border:1px solid #e5d9dd;">
        <h1 style="color:#b86b7d; font-size:24px; margin-bottom:10px;">Welcome, ${user.name}! 💜</h1>
        <p style="font-size:15px; line-height:1.6; color:#6b5b62;">
          We are thrilled to have you join Aviraa. Our mission is to empower women to reach their career goals while nurturing physical and emotional well-being.
        </p>
        <div style="background:#fef9f4; padding:16px; border-radius:12px; border-left:4px solid #b86b7d; margin:20px 0;">
          <h3 style="margin:0 0 8px 0; color:#1a1a2e; font-size:16px;">What you can do today:</h3>
          <ul style="margin:0; padding-left:20px; color:#6b5b62; font-size:14px;">
            <li>💼 Check out your personalized Career Roadmap</li>
            <li>🌿 Log daily mood & stress tracking</li>
            <li>🤖 Chat 24/7 with your empathetic AI Companion</li>
            <li>🤝 Connect with expert female mentors</li>
          </ul>
        </div>
        <p style="font-size:14px; color:#6b5b62;">Keep growing and thriving,<br><strong>Team Aviraa 🌱</strong></p>
      </div>
    </div>
  `;

  return deliverEmail(user.email, subject, html);
}

/**
 * Sends a rich progress digest email
 */
async function sendProgressDigest(user, careerData = {}, wellnessData = {}) {
  const subject = `✨ Your Aviraa Digest for ${new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
  const skillsCount = (user.skills || []).length;
  const mood = wellnessData.mood || 'Balanced';
  const streak = wellnessData.streakDays || 1;

  const html = `
    <div style="font-family: 'Helvetica Neue', Arial, sans-serif; background:#fdfaf7; padding:30px; color:#1a1a2e;">
      <div style="max-width:580px; margin:0 auto; background:white; border-radius:16px; padding:30px; box-shadow:0 8px 24px rgba(0,0,0,0.05); border:1px solid #e5d9dd;">
        <div style="text-align:center; margin-bottom:20px;">
          <span style="background:#b86b7d; color:white; padding:6px 16px; border-radius:20px; font-weight:600; font-size:12px; text-transform:uppercase;">Daily Digest</span>
          <h2 style="color:#1a1a2e; margin-top:12px;">Hello ${user.name.split(' ')[0]}, here is your growth snapshot! 🌸</h2>
        </div>

        <div style="display:flex; gap:12px; margin-bottom:20px;">
          <div style="flex:1; background:#fef3e4; padding:16px; border-radius:12px; text-align:center;">
            <div style="font-size:24px; font-weight:bold; color:#c4855a;">${skillsCount}</div>
            <div style="font-size:12px; color:#6b5b62; font-weight:600;">Active Skills</div>
          </div>
          <div style="flex:1; background:#e8f2ec; padding:16px; border-radius:12px; text-align:center;">
            <div style="font-size:24px; font-weight:bold; color:#7a9e8a;">${streak} Days</div>
            <div style="font-size:12px; color:#6b5b62; font-weight:600;">Wellness Streak</div>
          </div>
          <div style="flex:1; background:#fdf7f9; padding:16px; border-radius:12px; text-align:center;">
            <div style="font-size:24px; font-weight:bold; color:#b86b7d;">${mood}</div>
            <div style="font-size:12px; color:#6b5b62; font-weight:600;">Latest Mood</div>
          </div>
        </div>

        <div style="background:#fdfaf7; padding:16px; border-radius:12px; margin-bottom:20px; border:1px solid #e5d9dd;">
          <h4 style="margin:0 0 8px 0; color:#b86b7d;">💼 Career Highlight</h4>
          <p style="margin:0; font-size:14px; color:#6b5b62; line-height:1.5;">
            Target Role: <strong>${user.targetRole || 'Professional Growth'}</strong>.<br>
            Explore your updated learning roadmap and high-match opportunity recommendations in Aviraa!
          </p>
        </div>

        <div style="text-align:center; margin-top:24px;">
          <a href="http://localhost:8080/app.html" style="background:#b86b7d; color:white; padding:12px 28px; border-radius:24px; text-decoration:none; font-weight:600; font-size:14px; display:inline-block;">Open Aviraa Dashboard</a>
        </div>
      </div>
    </div>
  `;

  return deliverEmail(user.email, subject, html);
}

/**
 * Deliver helper (transporter or console log)
 */
async function deliverEmail(toEmail, subject, htmlContent) {
  const transporter = getTransporter();
  if (transporter) {
    try {
      const info = await transporter.sendMail({
        from: `"Aviraa Companion" <${process.env.SMTP_FROM || 'noreply@aviraa.app'}>`,
        to: toEmail,
        subject: subject,
        html: htmlContent
      });
      console.log(`✉️ Real Email sent to ${toEmail}: ${info.messageId}`);
      return { success: true, messageId: info.messageId, mode: 'smtp' };
    } catch (err) {
      console.error(`⚠️ SMTP Error: ${err.message}. Falling back to log mode.`);
    }
  }

  // Fallback logger mode (simulates successful email dispatch with clear output)
  console.log(`================ EMAIL DISPATCH (LOGGER MODE) ================`);
  console.log(`TO: ${toEmail}`);
  console.log(`SUBJECT: ${subject}`);
  console.log(`STATUS: Delivered successfully (Simulated)`);
  console.log(`==============================================================`);
  return { success: true, mode: 'simulated' };
}

module.exports = {
  sendWelcomeEmail,
  sendProgressDigest,
  deliverEmail
};
