# Aviraa 🌱

**AI-powered growth companion for women**

Empowering women to build successful careers while prioritizing their well-being.

## ✨ Features

- **💼 Career AI** — Personalized skill roadmaps, career guidance, resume analysis, interview prep
- **🌿 Wellness** — Cycle-aware productivity insights, mood & stress tracking, self-care routines
- **🤖 AI Companion** — Empathetic chatbot for career & wellness support (local keyword engine + optional Gemini/OpenAI)
- **🧭 Opportunities** — Curated jobs, mentorship programs & upskilling matches with ML-based scoring
- **🤝 Mentorship** — Request 1-on-1 sessions with expert mentors, persisted to database with email confirmation
- **📧 Email Notifications** — Welcome emails, application confirmations, mentorship updates, and daily progress digests

---

## 🧠 AI Companion Architecture

Aviraa uses a **dual-mode AI system** that works completely offline by default:

| Mode | Trigger | Engine | Description |
|------|---------|--------|-------------|
| **Local (default)** | Always active | `aiHelper.js` | Keyword-based intent classification, deterministic response templates, personalized with user context |
| **LLM (optional)** | `ENABLE_LLM=true` | `llmHelper.js` | Integrates with Gemini or OpenAI for deeper conversational responses |

### How the Local Engine Works (`backend/utils/aiHelper.js`)

1. **Intent classification** — Uses TF-IDF-like keyword scoring against known intents (`career`, `wellness`, `tech`, `learning`, `general`)
2. **Context injection** — Pulls user's name, skills, career goals, wellness data, and cycle phase into responses
3. **Daily insights** — Deterministic selection based on career progress, wellness streak & cycle phase
4. **Opportunity scoring** — Multi-factor: role alignment, experience, skills, remote preference

→ No external API keys required. Fully offline.

---

## 🚀 Quick Start

### Prerequisites

- Node.js v18+
- MongoDB (local or Atlas)
- npm

### Local Development

```bash
# 1. Clone and install
git clone <repo-url>
cd backend
npm install

# 2. Configure environment
cp .env.example .env
# Edit .env with your MongoDB URI and JWT_SECRET

# 3. Start MongoDB (if running locally)
mongod

# 4. Run the backend
npm run dev
```

The backend starts at `http://localhost:5000`.

### Docker Compose

```bash
docker-compose up --build
```

This starts both the backend and frontend containers with MongoDB.

### Frontend

Open `frontend/index.html` or serve via any static file server. The frontend connects to the backend at `http://localhost:5000`.

---

## 🔐 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PORT` | No | `5000` | Server port |
| `MONGODB_URI` | Yes | `mongodb://localhost:27017/aviraa` | MongoDB connection string |
| `JWT_SECRET` | Yes | — | Secret for signing JWT tokens |
| `JWT_EXPIRE` | No | `30d` | JWT expiration duration |
| `CLIENT_URL` | No | `http://localhost:8080` | Allowed CORS origin |
| `SMTP_HOST` | No | — | SMTP server host (email notifications) |
| `SMTP_PORT` | No | `587` | SMTP port |
| `SMTP_SECURE` | No | `false` | Use TLS for SMTP |
| `SMTP_USER` | No | — | SMTP username |
| `SMTP_PASS` | No | — | SMTP password |
| `SMTP_FROM` | No | `noreply@aviraa.app` | From address for emails |
| `NOTIFICATION_EMAIL` | No | `SMTP_USER` | Where to send admin notifications |
| `ENABLE_LLM` | No | `false` | Set to `true` to enable LLM mode |
| `GEMINI_API_KEY` | No | — | Google Gemini API key (if `ENABLE_LLM=true`) |
| `OPENAI_API_KEY` | No | — | OpenAI API key (if `ENABLE_LLM=true`) |

> **Email is optional.** If SMTP is not configured, all emails (welcome, applications, mentorship confirmations, digests) are logged to the console in a simulated delivery mode.
---

## 📡 API Overview

All API endpoints require a valid JWT token in the `Authorization: Bearer <token>` header, except `POST /api/auth/signup` and `POST /api/auth/login`.

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/auth/signup` | Register new user |
| `POST` | `/api/auth/login` | Login |
| `GET` | `/api/auth/profile` | Get user profile |
| `PUT` | `/api/auth/profile` | Update user profile |
| `POST` | `/api/auth/send-digest` | Trigger progress digest email |

### Career AI

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/career` | Get career profile & skills |
| `PUT` | `/api/career/skills` | Add/update a skill |
| `POST` | `/api/career/goals` | Add a career goal |
| `GET` | `/api/career/insights` | Generate personalized AI insights |
| `GET` | `/api/career/learning-path` | Personalized learning path with real course links |
| `POST` | `/api/career/analyze-resume` | ATS resume analysis |
| `POST` | `/api/career/interview-prep` | Generate mock interview question |
| `GET` | `/api/career/export-plan` | Download career plan as text file |

### Wellness

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/wellness` | Get wellness profile |
| `POST` | `/api/wellness/mood` | Log daily mood |
| `POST` | `/api/wellness/cycle` | Update cycle data |
| `GET` | `/api/wellness/insights` | Cycle-aware productivity insights |

### AI Companion

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/chat` | Send message to AI companion |

### Opportunities

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/opportunities` | List opportunities (ML-scored) |
| `POST` | `/api/opportunities/:id/save` | Save an opportunity |
| `POST` | `/api/opportunities/:id/apply` | Apply (saves + sends confirmation email) |

### Mentorship

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/mentorship` | List mentors (match-scored) |
| `POST` | `/api/mentorship/:id/request` | Request session (persisted to DB + email) |
| `GET` | `/api/mentorship/requests/me` | Get user's mentorship requests |
| `PATCH` | `/api/mentorship/requests/:id` | Update request status |

### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/dashboard` | Aggregated overview (career + wellness) |
---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Aviraa System                      │
├──────────────────┬──────────────────┬────────────────┤
│   Frontend       │    Backend       │    Database    │
│                  │                  │                │
│  ┌────────────┐  │  ┌────────────┐  │  ┌──────────┐ │
│  │ app.html   │  │  │ server.js  │  │  │ MongoDB  │ │
│  │ login.html │  │  │  ├─ auth    │  │  │          │ │
│  │ signup.html│  │  │  ├─ career  │  │  │ Users    │ │
│  │ index.html │  │  │  ├─ wellness│  │  │ Careers  │ │
│  │ profile.html│  │  │  ├─ chat   │  │  │ Wellness │ │
│  └────────────┘  │  │  ├─ opps    │  │  │ Mentors  │ │
│  ┌────────────┐  │  │  ├─ mentor  │  │  │ Opps     │ │
│  │ JS (API)   │──┼─▶│  └─ dash   │──┼──▶│ Requests │ │
│  │ CSS        │  │  │             │  │  └──────────┘ │
│  └────────────┘  │  │ aiHelper.js │  │                │
│                  │  │ llmHelper   │  │                │
│                  │  │ emailSender │  │                │
└──────────────────┴──────────────────┴────────────────┘
       HTML served          Express REST API           Mongoose ODM
     from static /
```

### Directory Layout

```
backend/
├── config/
│   └── db.js                  # MongoDB connection
├── controllers/
│   ├── authController.js       # Signup, login, profile, digest
│   ├── careerController.js     # Skills, goals, insights, resume, interview
│   ├── chatController.js       # AI companion chat
│   ├── dashboardController.js  # Aggregated dashboard
│   ├── mentorshipController.js # Mentors, requests, status
│   ├── opportunityController.js # Jobs/scholarships with apply
│   └── wellnessController.js   # Mood, cycle, insights
├── middleware/
│   ├── auth.js                 # JWT protection
│   └── errorHandler.js         # Global error handler
├── models/
│   ├── Career.js
│   ├── Chat.js
│   ├── Mentor.js
│   ├── MentorshipRequest.js    # NEW - persisted mentorship requests
│   ├── Opportunity.js
│   ├── SavedOpportunity.js
│   ├── User.js
│   └── Wellness.js
├── routes/
│   ├── auth.js, career.js, chat.js, dashboard.js
│   ├── mentorship.js, opportunities.js, wellness.js
├── utils/
│   ├── aiHelper.js             # Local keyword-based AI engine
│   ├── contentSafety.js
│   ├── emailSender.js          # SMTP + console fallback
│   ├── llmHelper.js            # Optional Gemini/OpenAI
│   └── validators.js
├── server.js                   # Entry point
└── package.json
```

---

## 📧 Email System

Emails are sent via SMTP when configured, otherwise logged to console for development:

| Email Type | Trigger | Delivered To |
|------------|---------|-------------|
| **Welcome** | User signup | New user |
| **Application Confirmation** | Apply to opportunity | Applicant |
| **Mentorship Confirmation** | Request mentor session | Requester |
| **Progress Digest** | `POST /api/auth/send-digest` or daily cron | User |

Each uses `backend/utils/emailSender.js` → `deliverEmail()` which:
1. Tries SMTP (if `SMTP_HOST` env var is set)
2. Falls back to console log with full email content visible in server output

---

## 🛠️ What Was Implemented (Latest)

- **MentorshipRequest model** — Mongoose schema with timestamps, status enum, unique pending constraint
- **Persistent mentorship requests** — `POST /api/mentorship/:id/request` now saves to MongoDB and sends email
- **New mentorship endpoints** — `GET /api/mentorship/requests/me`, `PATCH /api/mentorship/requests/:id`
- **Real learning resource links** — All `url: '#'` replaced with real Coursera, freeCodeCamp, fast.ai, LinkedIn Learning URLs (open in new tab)
- **Application confirmation emails** — Apply to any opportunity triggers a confirmation email
- **Welcome email on signup** — New users receive a rich welcome email via SMTP or console
- **`nodemailer` added** — Properly declared in `package.json` for real email delivery when SMTP is configured
- **Updated README** — Full API docs, architecture diagram, setup guides, env vars

---

Built with 💜 for women everywhere.
