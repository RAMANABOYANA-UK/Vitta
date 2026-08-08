const Career = require('../models/Career');
const User = require('../models/User');
const { generateDailyInsight, generateAIResponse } = require('../utils/aiHelper');

// Learning resources keyed by skill category for personalized learning path generation
const LEARNING_RESOURCES = {
  'leadership': [
    { title: 'Leading High-Performing Teams', platform: 'Coursera', duration: '6 weeks', url: '#' },
    { title: 'Situational Leadership Masterclass', platform: 'LinkedIn Learning', duration: '3 hours', url: '#' }
  ],
  'product management': [
    { title: 'Product Management Essentials', platform: 'Coursera', duration: '8 weeks', url: '#' },
    { title: 'From Idea to Launch: PM Playbook', platform: 'Udemy', duration: '12 hours', url: '#' }
  ],
  'data science': [
    { title: 'Data Science with Python', platform: 'Coursera', duration: '10 weeks', url: '#' },
    { title: 'SQL for Data Analysis', platform: 'Mode Analytics', duration: '4 hours', url: '#' }
  ],
  'software': [
    { title: 'System Design for Interviews', platform: 'Educative', duration: '5 weeks', url: '#' },
    { title: 'Advanced JavaScript Patterns', platform: 'Frontend Masters', duration: '8 hours', url: '#' }
  ],
  'communication': [
    { title: 'Influential Communication', platform: 'Coursera', duration: '4 weeks', url: '#' },
    { title: 'Public Speaking for Professionals', platform: 'MasterClass', duration: '3 hours', url: '#' }
  ],
  'ai': [
    { title: 'AI for Everyone', platform: 'Coursera', duration: '4 weeks', url: '#' },
    { title: 'Building AI Products', platform: 'Udemy', duration: '10 hours', url: '#' }
  ],
  'general': [
    { title: 'Career Growth Fundamentals', platform: 'LinkedIn Learning', duration: '2 hours', url: '#' },
    { title: 'Personal Branding for Professionals', platform: 'Skillshare', duration: '90 min', url: '#' }
  ]
};

// Map a skill name to a learning resource bucket
function resourceBucketForSkill(skillName) {
  const s = String(skillName || '').toLowerCase();
  if (/lead|manage|director|senior|supervis/i.test(s)) return 'leadership';
  if (/product|pm/i.test(s)) return 'product management';
  if (/data|analytics|sql|statistic/i.test(s)) return 'data science';
  if (/python|javascript|java|react|node|code|software|developer|engineer|frontend|backend|full.?stack/i.test(s)) return 'software';
  if (/communic|present|speak|negotiat|writing/i.test(s)) return 'communication';
if (/ai|machine learn|ml|deep/i.test(s)) return 'ai';
  return 'general';
}

// Return the effective skill list for a user, preferring the Career document
// but falling back to the User profile skills when the Career doc is empty.
// This keeps Career AI in sync with the "Profile" page data reliably.
function resolveSkills(careerSkills = [], user) {
  const sanitize = (v) => String(v || '').trim();
  const careerSkillsClean = (careerSkills || [])
    .filter((s) => s && sanitize(s.name))
    .map((s) => ({ name: sanitize(s.name), level: s.level || 0 }));
  if (careerSkillsClean.length > 0) return careerSkillsClean;

  const userSkills = (user?.skills || [])
    .filter((s) => s && sanitize(s.name))
    .map((s) => ({ name: sanitize(s.name), level: s.level || 0 }));
  return userSkills;
}

const getCareer = async (req, res, next) => {
  try {
    let career = await Career.findOne({ user: req.user._id });
    if (!career) {
      career = await Career.create({ user: req.user._id });
    }

    // Fallback: if the Career doc has no skills but the User profile does,
    // merge the profile's skills in so Career AI reflects profile data reliably.
    if ((!career.skills || career.skills.length === 0)) {
      const user = await User.findById(req.user._id);
      const userSkills = (user?.skills || []).filter((s) => s && s.name);
      if (userSkills.length > 0) {
        career.skills = userSkills.map((s) => ({
          name: String(s.name || '').trim(),
          level: Math.min(100, Math.max(0, Number(s.level) || 50)),
          category: s.category || 'General'
        }));
      }
    }
    res.json(career);
  } catch (error) {
    next(error);
  }
};

const updateSkills = async (req, res, next) => {
  try {
    const { name, level } = req.body;
    let career = await Career.findOne({ user: req.user._id });
    
    if (!career) {
      career = await Career.create({ user: req.user._id });
    }

    const skillIndex = career.skills.findIndex(s => s.name === name);
    if (skillIndex > -1) {
      career.skills[skillIndex].level = level;
    } else {
      career.skills.push({ name, level, category: 'General' });
    }

    await career.save();
    res.json(career);
  } catch (error) {
    next(error);
  }
};

const addGoal = async (req, res, next) => {
  try {
    const { title, targetDate } = req.body;
    let career = await Career.findOne({ user: req.user._id });
    
    if (!career) {
      career = await Career.create({ user: req.user._id });
    }

    career.goals.push({ title, targetDate });
    await career.save();
    res.json(career);
  } catch (error) {
    next(error);
  }
};

// ─── Resume Analyser ────────────────────────────────────────────────────────
// Extracts skills, computes an ATS score, and returns improvement suggestions.
const COMMON_SKILLS = [
  'python', 'javascript', 'typescript', 'java', 'c++', 'c#', 'sql', 'nosql', 'mongodb', 'postgresql',
  'react', 'node', 'nodejs', 'express', 'angular', 'vue', 'django', 'flask', 'html', 'css',
  'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'terraform', 'ci/cd', 'git', 'linux',
  'machine learning', 'deep learning', 'ai', 'nlp', 'data analysis', 'data science', 'tensorflow', 'pytorch',
  'project management', 'agile', 'scrum', 'product management', 'leadership', 'communication',
  'public speaking', 'negotiation', 'marketing', 'sales', 'finance', 'excel', 'powerpoint',
  'ui/ux', 'figma', 'graphic design', 'seo', 'content writing', 'recruiting', 'hr'
];

const TARGET_KEYWORDS = ['achieved', 'increased', 'improved', 'reduced', 'led', 'managed', 'created', 'developed', 'launched', 'delivered', 'saved', 'grew', 'built', 'designed', 'shipped', '%', '\$', 'team', 'cross-functional', 'stakeholders'];

const analyzeResume = async (req, res, next) => {
  try {
    const { resumeText } = req.body;
    if (!resumeText || !resumeText.trim()) {
      return res.status(400).json({ message: 'Resume text is required' });
    }

    const text = resumeText.toLowerCase();
    const words = resumeText.split(/\s+/).length;

    // Extract matched skills
    const foundSkills = COMMON_SKILLS.filter(skill => text.includes(skill));
    const missingSkills = COMMON_SKILLS.filter(skill => !text.includes(skill)).slice(0, 8);

    // ATS score heuristics
    let score = 40;
    if (words >= 300 && words <= 800) score += 15;
    if (words > 800) score += 10;
    if (foundSkills.length > 0) score += Math.min(foundSkills.length, 10) * 2;
    if (TARGET_KEYWORDS.some(kw => text.includes(kw))) score += 10;
    if (/\d{4}/.test(text)) score += 5; // dates present
    if (/@/.test(text) || /linkedin\.com/.test(text)) score += 5; // contact/linkedin
    if (/education|degree|university|college|b\.?tech|m\.?tech|b\.?s|m\.?s|phd/i.test(text)) score += 5;
    score = Math.min(score, 98); // never 100, always room to improve

    const suggestions = [];
    if (words < 300) suggestions.push('Your resume is under 300 words. Expand it with more detail on your experience and achievements.');
    if (words > 800) suggestions.push('Your resume may be too long. Aim for 1-2 pages (roughly 300-800 words) for best ATS readability.');
    if (foundSkills.length === 0) suggestions.push('No in-demand skills detected. Add a skills section with relevant keywords for your target role.');
    if (foundSkills.length > 0 && foundSkills.length < 4) suggestions.push('Add more relevant skills. A strong resume lists 5-10 relevant technical or soft skills.');
    if (!TARGET_KEYWORDS.some(kw => text.includes(kw))) suggestions.push('Include quantified achievements (e.g. "increased sales by 30%", "led a team of 6"). ATS systems reward measurable results.');
    if (!/\d{4}/.test(text)) suggestions.push('Add dates to your experience and education entries — recruiters expect clear timeframes.');
    if (!/@/.test(text) && !/linkedin\.com/.test(text)) suggestions.push('Include a professional email and LinkedIn URL in your contact section.');
    if (!/education|degree|university|college/i.test(text)) suggestions.push('Add an Education section with your degree and institution.');
    if (suggestions.length === 0) suggestions.push('Great structure! Add more specific numbers and tailor keywords per job application to push your score higher.');

    res.json({
      score,
      wordCount: words,
      skillsFound: foundSkills,
      missingSkills,
      suggestions: suggestions.slice(0, 6)
    });
  } catch (error) {
    next(error);
  }
};

// ─── Interview Prep (mock interview) ────────────────────────────────────────
const getInterviewQuestion = async (req, res, next) => {
  try {
    const { role, level } = req.body;
    const targetRole = role || 'your target role';
    const targetLevel = level || 'mid-level';

    const questions = [
      {
        question: `Tell me about yourself and why you are the right fit for this ${targetLevel} ${targetRole} role.`,
        tips: 'Structure your answer: past → present → future. Mention 2-3 relevant achievements and tie them to the role.',
        modelAnswer: `I'm a ${targetLevel} professional with a strong track record in ${targetRole}. Over the past few years I've led key initiatives, improved outcomes, and collaborated cross-functionally. I'm now looking to bring that experience to a role where I can own bigger impact.`
      },
      {
        question: `Describe a challenge you faced in a previous ${targetRole} role and how you overcame it.`,
        tips: 'Use the STAR method: Situation, Task, Action, Result. Quantify the outcome where possible.',
        modelAnswer: `Situation: our team missed a tight deadline. Task: I needed to realign priorities. Action: I facilitated a re-plan, cut non-essential scope, and reallocated resources. Result: we shipped on time and the client renewed.`
      },
      {
        question: `Where do you see yourself in 5 years, and how does this role fit into that vision?`,
        tips: 'Show ambition aligned with growth. Connect the role to your long-term career goals.',
        modelAnswer: `In 5 years I see myself leading a team in the ${targetRole} space. This role is the right next step because it lets me build the skills and ownership required to grow into a senior leadership position.`
      },
      {
        question: `How do you handle working with difficult stakeholders or cross-functional teams?`,
        tips: 'Emphasize communication, empathy, alignment on goals, and data-driven decisions.',
        modelAnswer: `I focus on understanding each stakeholder's priorities, communicating transparently, and using data to align decisions. I set clear expectations early and keep everyone updated to avoid surprises.`
      },
      {
        question: `Tell me about a time you showed leadership or took initiative.`,
        tips: 'Pick a concrete example. Highlight ownership, decision-making, and the positive outcome.',
        modelAnswer: `I identified a process bottleneck and proactively proposed a solution. I drove the change, got buy-in, and the improvement reduced turnaround time by 25%.`
      }
    ];

    const idx = Math.floor(Math.random() * questions.length);
    const picked = questions[idx];
    res.json({
      question: picked.question,
      tips: picked.tips,
      modelAnswer: picked.modelAnswer,
      index: idx,
      total: questions.length
    });
  } catch (error) {
    next(error);
  }
};

// ─── Personalized Career Insights ───────────────────────────────────────────
// Builds dynamic, personalized AI recommendations from the user's profile,
// skills, and goals using the existing aiHelper engine. Persists to career.aiInsights.
const getCareerInsights = async (req, res, next) => {
  try {
    const [career, user] = await Promise.all([
      Career.findOne({ user: req.user._id }),
      User.findById(req.user._id)
    ]);

const sanitize = (v) => String(v || '').trim();
    const skills = resolveSkills(career?.skills, user);
    const goals = career?.goals || [];
    const currentRole = sanitize(user?.currentRole);
    const targetRole = sanitize(user?.targetRole);
    const experience = Number(user?.experience) || 0;

    // Build context for the AI engine
    const ctx = {
      user: {
        name: user?.name || 'there',
        currentRole,
        targetRole,
        experience,
        skills: skills.map(s => s.name),
        cycleData: user?.cycleData || {}
      },
      career: { skills, goals, experience },
      wellness: {}
    };

    // 1. AI daily insight (career-focused)
    const insight = generateDailyInsight(ctx);

    // 2. Detect top skill gaps (lowest-level skills = priority)
    const skillGaps = skills
      .filter(s => s.name)
      .sort((a, b) => a.level - b.level)
      .slice(0, 3)
      .map(s => ({ name: s.name, level: s.level, gap: Math.max(0, 90 - s.level) }));

    // 3. Role-transition recommendation using the AI engine
    let roleAdvice = null;
    if (targetRole && currentRole) {
      const ai = generateAIResponse(
        `I want to move from ${currentRole} to ${targetRole}. What should I focus on?`,
        ctx
      );
      roleAdvice = {
        intent: ai.intent,
        category: ai.category,
        recommendation: ai.response
      };
    }

    // 4. Build the personalized plan
    const plan = {
      summary: insight?.insight || 'Focus on closing your biggest skill gap to reach your target role.',
      currentRole,
      targetRole,
      experience,
      skillGaps,
      nextSteps: buildNextSteps({ skills, goals, targetRole, experience }),
      roleAdvice
    };

    // Persist as an AI insight
    if (career) {
      career.aiInsights.push({
        message: plan.summary,
        category: 'career',
        date: new Date()
      });
      if (career.aiInsights.length > 20) {
        career.aiInsights = career.aiInsights.slice(-20);
      }
      await career.save();
    }

    res.json(plan);
  } catch (error) {
    next(error);
  }
};

// Build a concrete list of next steps based on the user's profile
function buildNextSteps({ skills, goals, targetRole, experience }) {
  const steps = [];
  if (skills.length === 0) {
    steps.push('Add 3-5 core skills to your profile so I can build your personalized roadmap.');
  } else {
    const weakest = skills.slice().sort((a, b) => a.level - b.level)[0];
    if (weakest) {
      steps.push(`Focus on strengthening "${weakest.name}" (currently ${weakest.level}%) over the next 30 days.`);
    }
    const nextWeakest = skills.slice().sort((a, b) => a.level - b.level)[1];
    if (nextWeakest) {
      steps.push(`Dedicate weekly practice time to "${nextWeakest.name}" to close the gap toward your target.`);
    }
  }
  if (targetRole) {
    steps.push(`Build a portfolio/resume tailored to ${targetRole} with quantified achievements.`);
    steps.push('Practice mock interviews using the Interview Prep tool to build confidence.');
  }
  if (goals.length > 0) {
    const activeGoals = goals.filter(g => g.status === 'active');
    if (activeGoals.length > 0) {
      steps.push(`Track progress on your active goal: "${activeGoals[0].title}".`);
    }
  }
  if (experience < 3) {
    steps.push('Seek mentorship and shadowing opportunities to accelerate growth.');
  }
  if (steps.length === 0) {
    steps.push('Set a concrete career goal and start building your skill portfolio.');
  }
  return steps.slice(0, 5);
}

// ─── Personalized Learning Path ─────────────────────────────────────────────
// Builds a recommended learning path from the user's skill gaps.
const getLearningPath = async (req, res, next) => {
  try {
    const [career, user] = await Promise.all([
      Career.findOne({ user: req.user._id }),
      User.findById(req.user._id)
    ]);

const sanitize = (v) => String(v || '').trim();
    const skills = resolveSkills(career?.skills, user);
    const targetRole = sanitize(user?.targetRole);

    // Sort skills by level ascending (weakest first) to prioritize learning
    const sorted = skills.slice().sort((a, b) => a.level - b.level);

    const pathSteps = [];
    const seenBuckets = new Set();

    // Prioritize the weakest skills first
    for (const skill of sorted.slice(0, 4)) {
      const bucket = resourceBucketForSkill(skill.name);
      if (seenBuckets.has(bucket)) continue;
      seenBuckets.add(bucket);
      const resources = LEARNING_RESOURCES[bucket] || LEARNING_RESOURCES.general;
      pathSteps.push({
        priority: pathSteps.length + 1,
        skill: skill.name,
        currentLevel: skill.level,
        targetLevel: Math.min(90, skill.level + 40),
        resources: resources.slice(0, 2).map(r => ({ ...r }))
      });
    }

    // If no skills, give a general starter path
    if (pathSteps.length === 0) {
      pathSteps.push({
        priority: 1,
        skill: 'Career Foundations',
        currentLevel: 0,
        targetLevel: 60,
        resources: LEARNING_RESOURCES.general.slice(0, 2).map(r => ({ ...r }))
      });
      pathSteps.push({
        priority: 2,
        skill: targetRole ? `${targetRole} Skills` : 'Role-Specific Skills',
        currentLevel: 0,
        targetLevel: 60,
        resources: LEARNING_RESOURCES.general.slice(0, 2).map(r => ({ ...r }))
      });
    }

    res.json({ targetRole, steps: pathSteps });
  } catch (error) {
    next(error);
  }
};

// ─── Export Career Plan ─────────────────────────────────────────────────────
const exportCareerPlan = async (req, res, next) => {
  try {
    const project = await Career.findOne({ user: req.user._id });
    const user = await require('mongoose').model('User').findById(req.user._id);

    const skills = project?.skills || [];
    const goals = project?.goals || [];
    const currentRole = user?.currentRole || 'Current role';
    const targetRole = user?.targetRole || 'Target role';

    const lines = [];
    lines.push('AVIRAA CAREER PLAN');
    lines.push('==================');
    lines.push('');
    lines.push(`Generated: ${new Date().toLocaleDateString()}`);
    lines.push('');
    lines.push(`Current Role: ${currentRole}`);
    lines.push(`Target Role:  ${targetRole}`);
    lines.push('');
    lines.push('GOALS');
    lines.push('-----');
    if (goals.length === 0) {
      lines.push('- No goals set yet. Add goals in the Career AI page.');
    } else {
      goals.forEach(g => lines.push(`- ${g.title} (${g.status}${g.targetDate ? ' · ' + new Date(g.targetDate).toLocaleDateString() : ''})`));
    }
    lines.push('');
    lines.push('SKILLS');
    lines.push('------');
    if (skills.length === 0) {
      lines.push('- No skills added yet.');
    } else {
      skills.forEach(s => lines.push(`- ${s.name}: ${s.level}%`));
    }
    lines.push('');
    lines.push('RECOMMENDED NEXT STEPS');
    lines.push('----------------------');
    lines.push('1. Focus on your top skill gap for the next 30 days.');
    lines.push('2. Add quantified achievements to your resume and LinkedIn.');
    lines.push('3. Practice mock interviews using the Interview Prep tool.');
    lines.push('4. Set one measurable goal each week and track progress.');
    lines.push('');
    lines.push('Built with care by Aviraa 💜');

    const planText = lines.join('\n');
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.setHeader('Content-Disposition', `attachment; filename="aviraa-career-plan-${new Date().toISOString().split('T')[0]}.txt"`);
    res.send(planText);
  } catch (error) {
    next(error);
  }
};

module.exports = { getCareer, updateSkills, addGoal, analyzeResume, getInterviewQuestion, getCareerInsights, getLearningPath, exportCareerPlan };
