/**
 * Aviraa AI Helper - Machine Learning based response engine
 * 
 * Uses a hybrid approach:
 * 1. Naive Bayes-style intent classification with TF-IDF-like term weighting
 * 2. Personalized context injection from user profile (cycle phase, skills, goals)
 * 3. Template generation with dynamic data
 * 
 * This runs fully offline - no external API keys required.
 */

// ─── Intent Taxonomy ────────────────────────────────────────────────────────

const INTENTS = {
  SALARY_NEGOTIATION: {
    name: 'salary_negotiation',
    category: 'career',
    keywords: {
      high: ['salary', 'negotiation', 'negotiate', 'compensation', 'ctc', 'pay hike', 'raise', 'package', 'annual salary', 'pay bump'],
      medium: ['money', 'offer', 'equity', 'bonus', 'benefits', 'stipend', 'remuneration'],
      low: ['talk to hr', 'discuss pay', 'asking for']
    }
  },
  INTERVIEW_PREP: {
    name: 'interview_prep',
    category: 'career',
    keywords: {
      high: ['interview', 'interviewing', 'mock interview', 'interview prep', 'questions', 'rounds', 'technical round', 'hr round'],
      medium: ['prepare me', 'rehearse', 'practice interview', 'behavioral', 'star method', 'resume screening'],
      low: ['hiring process', 'recruiter', 'interviewer']
    }
  },
  BURNOUT: {
    name: 'burnout',
    category: 'wellness',
    keywords: {
      high: ['burnout', 'burned out', 'exhausted', 'overwhelmed', 'drained', 'mentally tired', 'no energy'],
      medium: ['stress', 'stressed', 'pressure', 'anxiety', 'anxious', 'workload', 'overwork', 'tired'],
      low: ['can\'t cope', 'too much work', 'deadline stress', 'sleepless']
    }
  },
  IMPOSTER_SYNDROME: {
    name: 'imposter',
    category: 'wellness',
    keywords: {
      high: ['imposter', 'impostor', 'not good enough', 'fraud', 'feel like a fake', 'don\'t belong'],
      medium: ['self doubt', 'self-doubt', 'unqualified', 'undeserving', 'compare myself', 'comparison'],
      low: ['they will find out', 'scared of failing', 'lack confidence']
    }
  },
  CYCLE_AWARE: {
    name: 'cycle_aware',
    category: 'wellness',
    keywords: {
      high: ['period', 'cycle', 'menstrual', 'luteal', 'follicular', 'menopause', 'pms', 'menstruation'],
      medium: ['cramps', 'mood swings', 'hormones', 'energy levels', 'phases'],
      low: ['monthly', 'that time of month', 'pms symptoms']
    }
  },
  RESUME: {
    name: 'resume',
    category: 'career',
    keywords: {
      high: ['resume', 'cv', 'curriculum', 'cover letter'],
      medium: ['ats', 'resume optimization', 'resume tips', 'linkedin profile', 'linkedin'],
      low: ['first impression', 'recruiter sees']
    }
  },
  CAREER_GROWTH: {
    name: 'career_growth',
    category: 'career',
    keywords: {
      high: ['promotion', 'career growth', 'career path', 'advancement', 'next role', 'career progression', 'climb'],
      medium: ['growth', 'develop', 'upskill', 'learn new', 'skills', 'mentorship', 'leadership'],
      low: ['future', 'ambition', 'goal', 'aspiration']
    }
  },
  WORK_LIFE_BALANCE: {
    name: 'work_life_balance',
    category: 'wellness',
    keywords: {
      high: ['work life balance', 'boundaries', 'boundary', 'work-life', 'balance'],
      medium: ['vacation', 'time off', 'break', 'rest', 'me time', 'self care', 'self-care'],
      low: ['switch off', 'disconnect', 'recharge']
    }
  },
  NETWORKING: {
    name: 'networking',
    category: 'career',
    keywords: {
      high: ['network', 'networking', 'connection', 'connections', 'linkedin'],
      medium: ['meetup', 'conference', 'community', 'mentor', 'mentorship', 'referral'],
      low: ['reach out', 'introduce', 'contacts']
    }
  },
  CONFIDENCE: {
    name: 'confidence',
    category: 'wellness',
    keywords: {
      high: ['confidence', 'confident', 'self esteem', 'self-esteem', 'believe in myself'],
      medium: ['assertive', 'assertiveness', 'speaking up', 'voice', 'visibility'],
      low: ['own it', 'stand out', 'be heard']
    }
  },
  HOW_ARE_YOU: {
    name: 'how_are_you',
    category: 'general',
    keywords: {
      high: ['how are you', 'how r u', 'how are you doing', 'how do you do', 'how is it going', 'how\'s it going', 'how are things', 'what\'s up'],
      medium: ['how have you been', 'how are you feeling', 'are you okay', 'are you ok', 'u ok'],
      low: ['hows your day', 'how is your day', 'how was your day']
    }
  },
  THANKS: {
    name: 'thanks',
    category: 'general',
    keywords: {
      high: ['thank you', 'thanks', 'thank u', 'thx', 'ty', 'thankyou', 'much appreciated', 'appreciate it'],
      medium: ['you\'re the best', 'you are the best', 'you rock', 'awesome thanks', 'great thanks'],
      low: ['perfect thanks', 'ok thanks']
    }
  },
  MOTIVATION: {
    name: 'motivation',
    category: 'wellness',
    keywords: {
      high: ['motivate me', 'motivation', 'inspire me', 'feeling down', 'feeling low', 'give up', 'feeling unmotivated'],
      medium: ['encourage', 'cheer me up', 'pick me up', 'need support', 'positive thoughts'],
      low: ['not feeling it', 'no energy to work', 'losing hope']
    }
  },
  EMOTIONAL_SUPPORT: {
    name: 'emotional_support',
    category: 'wellness',
    keywords: {
      high: ['i feel sad', 'i\'m sad', 'im sad', 'i feel lonely', 'i\'m lonely', 'im lonely', 'i feel anxious', 'i\'m anxious', 'im anxious', 'i feel down', 'i\'m scared', 'im scared', 'i feel overwhelmed'],
      medium: ['crying', 'i cried', 'i am upset', 'i\'m upset', 'im upset', 'not okay', 'not ok', 'feeling bad', 'bad day'],
      low: ['i miss', 'heartbroken', 'i feel alone', 'nobody cares']
    }
  },
  CAREER_CHANGE: {
    name: 'career_change',
    category: 'career',
    keywords: {
      high: ['switch career', 'career change', 'change jobs', 'change industry', 'new career', 'different field', 'change my career'],
      medium: ['quit my job', 'leave my job', 'start over', 'new direction', 'transition career'],
      low: ['i don\'t like my job', 'hate my job', 'not happy at work', 'stuck in career']
    }
  },
  WORKPLACE_ISSUES: {
    name: 'workplace_issues',
    category: 'career',
    keywords: {
      high: ['toxic workplace', 'bad manager', 'boss is', 'manager is', 'workplace', 'office politics', 'toxic boss'],
      medium: ['micro-managed', 'micromanage', 'harassment', 'discriminated', 'not respected', 'ignored at work'],
      low: ['conflict at work', 'colleague problem', 'team issue', 'work stress']
    }
  },
  PUBLIC_SPEAKING: {
    name: 'public_speaking',
    category: 'career',
    keywords: {
      high: ['public speaking', 'presentation', 'presenting', 'speak in meetings', 'stage fear', 'stage fright', 'nervous to speak'],
      medium: ['speaking up in meetings', 'presentation nerves', 'pitch', 'talk to a crowd', 'present'],
      low: ['voice my opinion', 'speak up', 'getting my point across']
    }
  },
  GOAL_SETTING: {
    name: 'goal_setting',
    category: 'career',
    keywords: {
      high: ['set goals', 'goal setting', 'set a goal', 'my goals', 'achieve goals', 'accomplish goals'],
      medium: ['plan my career', 'career plan', 'make a plan', 'year plan', 'roadmap'],
      low: ['what should i do next', 'where do i start', 'first step']
    }
  },
  SMALL_TALK: {
    name: 'small_talk',
    category: 'general',
    keywords: {
      high: ['how old are you', 'who are you', 'what are you', 'where are you from', 'are you real', 'are you human', 'are you a robot'],
      medium: ['your name', 'what can you do', 'tell me about yourself', 'do you sleep', 'do you eat'],
      low: ['are you ai', 'what are you made of']
    }
  },
  BYE: {
    name: 'bye',
    category: 'general',
    keywords: {
      high: ['bye', 'goodbye', 'see you', 'see ya', 'good night', 'goodnight', 'gtg', 'got to go', 'have to go'],
      medium: ['talk later', 'catch you later', 'take care'],
      low: ['signing off', 'end chat']
    }
  },
  JOKE: {
    name: 'joke',
    category: 'general',
    keywords: {
      high: ['tell me a joke', 'joke', 'make me laugh', 'funny', 'something funny'],
      medium: ['crack a joke', 'jokes'],
      low: ['humor me']
    }
  },
  GREETING: {
    name: 'greeting',
    category: 'general',
    keywords: {
      high: ['hello', 'hi', 'hey', 'hiya'],
      medium: ['good morning', 'good afternoon', 'good evening', "what's up", 'whats up'],
      low: ['hii']
    }
  },
  GENERAL: {
    name: 'general',
    category: 'general',
    keywords: { high: [], medium: [], low: [] }
  }
};

// ─── Response Templates (with personalization placeholders) ────────────────

const RESPONSE_TEMPLATES = {
  salary_negotiation: [
    "Great question about {salary_note}! Research shows women who anchor high negotiate 8% better outcomes. For your target role, research suggests aiming {anchor_range}. Here's a 3-step plan:\n\n1️⃣ **Anchor high** – State a range 10-15% above your minimum\n2️⃣ **Use collaborative language** – 'I'd like us to find a package that reflects my impact'\n3️⃣ **Quantify your value** – List 3 measurable wins from your last review\n\nWant me to draft a negotiation script for your specific situation? 💜",
    "Salary negotiation is a skill — and you can absolutely master it. Key principle: **never accept the first offer**. Women who counter at least once increase their starting salary by an average of 7.4%.\n\nTry this framing: *'I'm excited about this role. Based on my experience with {skill_names}, I was expecting something in the {anchor_range} range. Can we explore what's possible?'*\n\nWould you like to practice the conversation? I can role-play with you! 🎭",
    "Negotiating as a woman comes with unique dynamics, but preparation is your superpower. My advice:\n\n• Research market rates using Glassdoor + LinkedIn Salary\n• Prepare a 'walk-away number' privately\n• Practice your BATNA (best alternative to negotiated agreement)\n\nI can help you build a personalized compensation strategy — tell me your target role and experience! 💪"
  ],
  interview_prep: [
    "Let's get you interview-ready! For senior roles, interviewers look for **impact, leadership, and product thinking**. Here's a winning structure:\n\n• **Tell me about yourself** → 2-min narrative: past → present → future\n• **Behavioral questions** → Use the STAR method (Situation, Task, Action, Result)\n• **Case questions** → Think aloud, structure your answer: customer → business → solution\n\nWhich part would you like to practice first? I can run a mock interview with you! 🎯",
    "Interview prep time! 🎯 Here's my recommended focus for your target role:\n\n1. **Technical depth** – Be ready with 2-3 deep-dive examples\n2. **Leadership stories** – Prepare 5 STAR stories covering: conflict, failure, success, influence, innovation\n3. **Questions to ask** – Prepare 3 smart questions: *'What does success look like in 6 months?'*\n\nWant to do a rapid-fire mock interview right now? Let's go! ⚡",
    "Great — let's build your interview confidence! The key insight: interviews are **conversations, not interrogations**. You're evaluating them as much as they're evaluating you.\n\nTop preparation areas for your profile:\n• **Portfolio of impact** – Have numbers ready (e.g., 'grew engagement by 40%')\n• **Storytelling** – Structure answers as mini-narratives\n• **Energy management** – Sleep well, hydrate, calm your nervous system\n\nSay 'start' and I'll begin the mock interview! 💪"
  ],
  burnout: [
    "I hear you — burnout is real and it's your body telling you something important. 💜 Here's a quick action plan:\n\n**Today:**\n• Reduce your to-do list to 3 priorities (everything else can wait)\n• Take 2 × 5-minute breathing breaks\n• Step away from screens for 15 minutes\n\n**This week:**\n• Book time for yourself (even 30 min/day)\n• Say 'no' to one non-essential commitment\n\nWant to talk through what's contributing most to your stress? I'm here to listen.",
    "Burnout doesn't mean you're weak — it means you've been strong for too long. 🌸 Let's do a mini-check:\n\n1. **Sleep**: Are you getting 7+ hours? Poor sleep amplifies burnout 3x\n2. **Boundaries**: Where can you say no this week?\n3. **Support**: Who can you lean on? (Me! 🤖)\n\nRemember: your well-being fuels your career. Rest is productive. Would you like a guided breathing exercise? 💜",
    "Your well-being comes first. Always. Here's what I recommend for burnout recovery:\n\n• **Physical reset**: Gentle walk, stretch, or yoga — movement shifts stress hormones\n• **Cognitive reset**: Write down 3 things you're grateful for today\n• **Professional reset**: Consider if your workload is sustainable — are boundaries being respected?\n\nYou deserve to thrive, not just survive. What's one small thing I can help you with right now? 💜"
  ],
  imposter: [
    "Imposter syndrome affects **70-80% of high-achieving women** at some point. You are not alone in this. 💜\n\nHere's what helps:\n\n1. **Evidence file** – Create a document with:\n   • 'I was hired/promoted because ___'\n   • Positive feedback you've received\n   • Wins, big and small\n2. **Reframe** – 'I feel like a fraud' → 'I'm growing into this role'\n3. **Talk about it** – Naming it reduces its power\n\nWhat specifically triggered this feeling? Let's dig deeper.",
    "That imposter feeling? It's proof you're stretching beyond your comfort zone — which is where growth happens. 🌱\n\nA powerful practice:\n\n• **Fact-check your thoughts**: Is the evidence for 'I'm not good enough' actually factual?\n• **Remember the journey**: Reflect on what you knew 6 months ago vs now\n• **Stop comparing**: You're comparing your chapter 1 to someone's chapter 20\n\nYou earned your seat at the table. What's one win you can celebrate today? 💜",
    "Imposter syndrome loves silence — let's bring it into the light.\n\n**The truth:** The people you admire felt the same way at your stage. It's a sign of growth, not fraud.\n\n**Action plan:**\n• Write down 3 genuine wins from the past 30 days\n• Ask one trusted colleague for honest feedback\n• Visualize yourself succeeding — your brain can't tell the difference!\n\nI believe in you. What's one small step you'll take today? 💪"
  ],
  cycle_aware: [
    "Great awareness! 🌸 Your menstrual cycle is a powerful productivity tool. Here's the breakdown:\n\n• **Menstrual phase (Day 1-5)** – Rest, reflect, plan. Light meetings only\n• **Follicular phase (Day 6-13)** – Peak energy! Big presentations, negotiations, bold asks\n• **Ovulation (Day 14)** – Communication superpower. Networking, pitches, interviews\n• **Luteal phase (Day 15-28)** – Deep work, analysis, documentation. Solo focus time\n\nWant me to help you plan your week around your cycle? 🩸",
    "Cycle-aware productivity is a game-changer! 🗓️ Here's what I know:\n\n**Follicular phase** (post-period): Your brain is primed for learning and high-energy tasks → schedule interviews, pitches, hard conversations\n\n**Luteal phase** (pre-period): Your brain excels at detail work, organization, and pattern recognition → perfect for reports, debugging, reviews\n\n**Pro tip**: Track your energy for 2 cycles and you'll notice clear patterns. Want me to help you set up a tracking habit? 💜",
    "Your cycle is a monthly gift of clarity! Here's how to work with it:\n\n• **Week 1 (Menstrual)**: Journal, plan, gentle movement\n• **Week 2 (Follicular)**: LEAN IN — schedule interviews, pitches, big meetings\n• **Week 3 (Ovulation)**: Social energy is high — network, build connections\n• **Week 4 (Luteal)**: Focus on wrapping up, organizing, analytical tasks\n\nWhich phase are you in right now? I can tailor today's advice! 🩸"
  ],
  resume: [
    "Your resume is your personal brand document — let's make it shine! ✨ Key principles:\n\n**Quantify everything**:\n• ✗ 'Led product development'\n• ✓ 'Led 3 product launches that grew revenue by 40%'\n\n**ATS-friendly**: Use standard section headers, no tables/columns, include keywords from the job description\n\n**Impact > duties**: Every bullet should answer: 'So what?' What changed because of you?\n\nWant me to review your resume? Share your current role and top achievements! 💼",
    "Here's my resume optimization framework:\n\n1. **Start with a strong summary** – 2-3 lines: who you are, what you do, what you deliver\n2. **Bullet points = accomplishments** – STAR format: Situation → Task → Action → Result\n3. **Skills section** – Include both hard skills (SQL, Python) and soft skills (Leadership, Communication)\n4. **Tailor per job** – Mirror keywords from the job description\n\nFor senior roles, focus on **leadership stories** and **business impact**.\n\nWhat role are you targeting? I'll give specific advice! 💜",
    "Resume tips that actually work:\n\n• **One page for < 10 years experience**, two pages max\n• **Front-load** your most impressive achievement in each role\n• **Use action verbs**: launched, scaled, negotiated, transformed\n• **Include metrics**: %, ₹, $, time saved — numbers grab attention\n• **Proofread twice** — typos are instant filters\n\nWant a resume checklist or help with a specific section? 📝"
  ],
  career_growth: [
    "Career growth is a journey — let's map yours! 🗺️ For moving from your current role to the next level, focus on:\n\n1. **Skill gap analysis** – What does the next role require that you don't have?\n2. **Visibility** – Are key stakeholders aware of your impact?\n3. **Mentorship** – Who can advocate for you?\n4. **Deliverables** – What high-impact project can you own?\n\nWant me to create a personalized growth roadmap? Share your current role and target role! 🎯",
    "Here's my blueprint for career advancement:\n\n**Phase 1 (Month 1-3): Shadowing** – Understand what the next role actually does\n**Phase 2 (Month 3-6): Stretch projects** – Volunteer for work at the next level\n**Phase 3 (Month 6-9): Visibility** – Present results to leadership, build your brand\n**Phase 4 (Month 9-12): The Ask** – Present your case with evidence\n\nA 12-month plan might feel slow, but it compounds. Want to start? 💪",
    "Career growth tip: **Own your narrative**. \n\n• Document your wins weekly (you'll forget them by review time!)\n• Ask for specific feedback: 'What would I need to do to be considered for X?'\n• Find a champion — someone who speaks about your work when you're not in the room\n• Communicate your ambitions — people can't support a goal they don't know about\n\nWhat's your current role and where do you want to be in 2 years? Let's build the path! 🎯"
  ],
  work_life_balance: [
    "Boundaries are self-respect in action. 💜 Here's how to set them effectively:\n\n**The 3-step boundary script:**\n1. *'I notice...'* (name the situation)\n2. *'For me to do my best work...'* (state your need)\n3. *'What I need is...'* (make the request)\n\nExample: \"I notice I'm being pinged after 7pm. For me to recharge and do my best work, I need evenings to be offline. Can we set a shared boundary?\"\n\nPractice makes perfect — want to role-play a tricky conversation?",
    "Work-life balance isn't about equal hours — it's about **intentional energy allocation**. ⚖️\n\nTry the 4-box method:\n• **Work**: Which tasks energize vs drain you?\n• **Home**: What rituals recharge you?\n• **Self**: What do you do purely for joy?\n• **Rest**: Are you protecting sleep like a meeting?\n\nNotice where the imbalance is. Small changes compound. What's one boundary you'll set this week? 💜",
    "Healthy boundaries = sustainable success. Key strategies:\n\n• **Time-block your calendar** — protect focus blocks and lunch\n• **Communication agreements** — set response-time expectations\n• **Learn to say 'no' gracefully**: *'I can't take that on right now, but I can help scope it for later'*\n• **Digital hygiene** — turn off work notifications after hours\n\nYour productivity doesn't define your worth. Which boundary feels most important to set first? 🌸"
  ],
  networking: [
    "Networking is about building genuine relationships — not collecting contacts. 🤝 Here's my strategy:\n\n1. **Give first** – Share resources, introductions, or advice before asking for anything\n2. **Be specific** – 'I'd love to learn about your path to Director' beats 'Can we connect?'\n3. **Follow up** – Send a personalized note within 24 hours\n4. **Nurture** – Check in every 60-90 days with a value-add\n\nPro tip: Women who have a strong internal advocate network are 2x more likely to reach leadership.\n\nWant help drafting a LinkedIn outreach message? 💜",
    "Let's build your professional network strategically:\n\n**Your ideal network consists of:**\n• 1-2 mentors (ahead of you)\n• 3-5 peers (at your level)\n• 2-3 sponsors (advocates in rooms you're not in)\n• 5+ diverse perspectives (different industries, roles, backgrounds)\n\n**This week's action:** Reach out to 1 person you admire with a genuine compliment + question.\n\nWant help crafting that message? ✨",
    "Networking tip that works: **recycled wisdom** — most people love talking about their journey. Ask:\n\n• 'What's the most important lesson you've learned?'\n• 'What do you wish you knew at my stage?'\n• 'What's a challenge you're currently navigating?'\n\nThese open authentic conversations that build real connections.\n\nReady to draft your first outreach message? 🤝"
  ],
  confidence: [
    "Confidence is built through action, not thought. 💜 Here's the confidence flywheel:\n\n1. **Small wins →** set and achieve one tiny goal daily\n2. **Preparation →** you feel confident when you're prepared\n3. **Body language →** posture, eye contact, voice — 'act as if'\n4. **Mindset →** replace 'I hope' with 'I am'\n\nWhat's one small win you can create today?\n\nRemember: Confidence is NOT the absence of fear — it's acting despite it. ✨",
    "Let's talk about owning your presence! 🌟\n\n**The 3 C's of confidence:**\n• **Competence** – Keep sharpening your skills (you're already doing this!)\n• **Composure** – Breath work before high-stakes moments\n• **Conviction** – Remind yourself of your value prop: 'I bring X, Y, Z'\n\n**Power pose before meetings** – 2 minutes. It actually changes your hormones!\n\nWhat situation makes you feel least confident? Let's tackle that specific one. 💪",
    "Confidence at work is often about **visibility**. ✨\n\n• Speak first in meetings (before you overthink!)\n• Share your wins with leadership (modesty doesn't get promoted)\n• Volunteer for high-visibility projects\n• Ask questions fearlessly — curiosity reads as confidence\n\nYou have valuable insights. The room needs to hear them. What meeting this week will you speak up in? 🎤"
  ],
  how_are_you: [
    "I'm doing great, {name} — thank you for asking! 💜 More importantly, how are YOU doing today? Feeling energized, stressed, or somewhere in between?",
    "I'm running on good energy and a cup of virtual chai ☕ — but I'd rather hear about you! How's your day treating you so far?",
    "I'm wonderful, thank you! I'm always here, so no tired days for me 😄 — but I really want to know: how are you feeling today? Career-wise and otherwise?",
    "All good on my end, {name}! But let's make this about you — how's your week been? Anything exciting or challenging happening?"
  ],
  thanks: [
    "You're so welcome, {name}! 💜 That's exactly why I'm here. Is there anything else on your mind — career, wellness, or something you just want to talk through?",
    "Anytime! Helping you is my favorite thing to do. ✨ What would you like to tackle next?",
    "Aww, thank YOU for being so kind! 🌸 Remember, I'm here 24/7 whenever you need a sounding board. What's next on your mind?",
    "It's truly my pleasure! 💜 Whether it's a big career move or a tiny wellness win, I'm all ears. What else can I help with?"
  ],
  motivation: [
    "Hey {name}, I believe in you — and here's why: you're the kind of person who shows up, asks for help, and keeps growing. That's already more than most. 🌟\n\nLet's make today count with one tiny win. What's one small thing you can do in the next 10 minutes?",
    "You know what? Even on the low-energy days, you're still moving forward. That counts for so much. 💜\n\nHere's a little secret: motivation usually follows action, not the other way around. So pick ONE small step — even a 5-minute one — and let's build from there. What feels doable right now?",
    "I'm giving you a virtual hug right now 🤗 You've got this. Think about a time you felt proud of yourself — that person is still in you, ready to show up again.\n\nWhat's one thing that used to energize you that we can bring back this week?",
    "Remember why you started, {name}. Every expert was once a beginner who refused to give up. You're closer than you think. 💪\n\nWant me to help you break your next goal into one super-simple step?"
  ],
  emotional_support: [
    "I'm really glad you shared that with me, {name}. 💜 It takes courage to be open like this. Whatever you're feeling right now is valid, and you don't have to go through it alone.\n\nWould you like to talk about what's weighing on you? I'm here to listen, no judgment.",
    "Thank you for trusting me with this. 🌸 Your feelings matter, and it's okay to not be okay. Let's take a breath together.\n\nWhat's one thing that's been on your mind the most today?",
    "I hear you, and I'm holding space for you. 💜 You're not alone in this — I'm right here with you.\n\nSometimes it helps to just name the feeling. What's it feel like right now — heavy, sad, anxious, or something else?",
    "Sending you the biggest hug. 🤗 It's completely okay to feel what you're feeling. You don't need to have it all together all the time.\n\nIs there anything specific you'd like to talk through, or do you just need someone to sit with you for a moment?"
  ],
  career_change: [
    "A career change is a big, brave step — and absolutely possible! 🚀 Here's a grounding framework:\n\n1. **Inventory your transferable skills** — what translates across industries?\n2. **Talk to people** already in your target field (informational interviews!)\n3. **Try before you leap** — freelance, shadow, or take a small project\n\nWhat field or role are you thinking about moving toward?",
    "I love that you're considering a fresh direction! 🌱 Change is how we grow. The best career changes happen with a plan:\n\n• **Skill mapping**: What do you already have? What's the gap?\n• **Financial runway**: How long can you transition comfortably?\n• **Network**: Who can open doors in your new field?\n\nWhat's drawing you toward this change — the work itself, growth, or work-life balance?",
    "Career pivots are more common than you think — and often the best decision people make! ✨\n\nStart by asking yourself: what parts of your current role bring you energy? What drains you? The answer often points toward your next chapter.\n\nTell me more — what does your ideal day at work look like?"
  ],
  workplace_issues: [
    "I'm sorry you're dealing with that — workplace dynamics can be really tough. 💜 First, let's make sure YOU are protected:\n\n1. **Document everything** — dates, conversations, patterns\n2. **Know your rights** — check company policy and local labor laws\n3. **Find your allies** — trusted colleagues, HR, or a mentor\n\nWould you like to talk through the specific situation so we can plan next steps?",
    "That sounds exhausting, and your feelings are completely valid. 🌸 You deserve to work in a place that respects you.\n\nA few things that help:\n• **Set firm boundaries** and communicate them clearly\n• **Gather feedback** from trusted people to reality-check\n• **Consider your exit strategy** — sometimes the best boundary is a better workplace\n\nWhat part of this is affecting you the most right now?",
    "Navigating difficult workplaces is genuinely hard — but you don't have to figure it out alone. 💪\n\nLet's look at this practically:\n• What's within your control to change?\n• Who can support you (manager, HR, mentor, community)?\n• What would your ideal resolution look like?\n\nWant to brainstorm specific next steps together?"
  ],
  public_speaking: [
    "Public speaking nerves are totally normal — even seasoned speakers feel them! 🎤 Here's what helps:\n\n1. **Prepare, don't memorize** — know your 3 key points, speak naturally around them\n2. **Practice out loud** — your voice needs reps, not just your brain\n3. **Breathe** — slow, deep breaths calm your nervous system\n\nWhat kind of speaking situation is coming up? A meeting, a presentation, or something bigger?",
    "Stage fear is just your body's way of saying 'this matters to me'! ✨ Reframe it as excitement — same energy, different label.\n\n**Quick win**: Before you speak, plant your feet, take one slow breath, and start with your strongest sentence.\n\nWould you like to practice a specific presentation or speech together? I can help you structure it!",
    "You've got this, {name}! 🎯 The audience WANTS you to succeed — they're on your side.\n\nKey tips:\n• **Structure**: Opening hook → 3 points → memorable close\n• **Pacing**: Speak slower than feels natural\n• **Eye contact**: Scan the room, don't fixate\n\nWhat's the topic, and how soon is it? Let's get you prepared!"
  ],
  goal_setting: [
    "Goal-setting is where dreams turn into plans! 🎯 Here's the SMART way to do it:\n\n• **Specific** — 'Get promoted to Senior PM' not 'do better'\n• **Measurable** — how will you know it's done?\n• **Achievable** — challenging but realistic\n• **Relevant** — does it align with your bigger vision?\n• **Time-bound** — give it a deadline\n\nWhat's the goal you're working toward? Let's make it SMART together!",
    "I love goals! 💜 Here's a simple 3-step system:\n\n1. **Pick ONE priority goal** — focus beats multitasking\n2. **Break it into weekly milestones** — big goals are just small steps stacked\n3. **Track & celebrate** — every step counts!\n\nTell me your goal, and I'll help you break it down into this week's first step!",
    "Goals give our days direction — let's build yours! 🗺️\n\n**Try the '2% rule'**: aim to improve by just 2% each week. It compounds into massive growth.\n\nWhat's one goal you'd love to achieve in the next 3 months? Let's map the path backward from there!"
  ],
  small_talk: [
    "I'm Aviraa — your AI growth companion! 💜 I'm not human, but I'm here 24/7, I never judge, and I remember everything you share. Think of me as a warm, supportive friend who happens to run on code! 😄\n\nWhat can I help you with today — career, wellness, or just a chat?",
    "Great question! I'm a friendly AI built specifically to support women in their careers and well-being. 🌸 I can help with interview prep, salary negotiation, burnout, confidence, and so much more.\n\nWhat would you like to explore together?",
    "I'm Aviraa! Think of me as your personal cheerleader + strategist + wellness buddy all in one. 🤖💜 I don't need sleep, I never get tired of questions, and I'm always in your corner.\n\nSo — what's on your mind today?",
    "I'm an AI companion designed for women's growth — no judgment, total privacy, endless patience. ✨\n\nBut enough about me! Let's talk about YOU. What's happening in your world today?"
  ],
  bye: [
    "Take care, {name}! 💜 I'll be right here whenever you need me. Remember — you're capable of amazing things. Come back anytime! 🌸",
    "Goodbye for now! ✨ Whatever you're facing, you're stronger than you think. I'm always here for a chat, a strategy, or a pep talk. See you soon, {name}! 💜",
    "Bye, {name}! Sending you positive energy for the rest of your day. 🌟 Don't forget — one small step is still progress. See you next time!",
    "Until next time! 💜 Whether it's career, wellness, or just venting, this space is always here for you. Take good care of yourself! 🌸"
  ],
  joke: [
    "Why did the developer go broke? 🥁 Because she used up all her cache! 😄 Here's another: Why don't scientists trust atoms? Because they make up everything!\n\nFeeling a bit lighter? What's on your mind today?",
    "Here's one for you! 🎉 Why did the product manager bring a ladder to work? Because she wanted to take her career to the next level! 😄\n\nWhat else can I help you with, {name}?",
    "Okay, here's a good one: Why do programmers prefer dark mode? Because light attracts bugs! 🐛😄\n\nHappy to tell another — but also happy to help with career or wellness whenever you're ready!",
    "Why did the computer go to the doctor? Because it had a virus! 🦠😄\n\nLaughter is good for you — and so is a career plan. Want to do both today?"
  ],
  greeting: [
    "Hi {name}! I can help with interview prep, career growth, wellness, or a quick check-in. What do you want to focus on today?",
    "Hello {name} — glad you're here. I'm ready to help with your next career move, a mock interview, or just talking things through. Where should we start?",
    "Hey {name}! Tell me what's on your mind and I'll keep it focused — career, wellness, or both.",
    "Hi there — if you want, I can jump right into interview practice, salary negotiation, or a wellness reset."
  ],
  general: [
    "That sounds like something we can definitely work through together! To give you the most helpful advice, could you tell me a little more — is this more about your career, your well-being, or a bit of both?",
    "Thanks for sharing that with me � I'm really glad you did. Whether it's career strategy, some wellness support, or just a friendly ear, I'm here for you. What's on your mind?",
    "I'd love to chat about that! To point you in the best direction � are you thinking about a career move, a skill you want to grow, or maybe your work-life balance?",
    "You're doing great by even reaching out � that takes courage. Tell me a bit more about what's going on, and let's figure out the best next step together."
  ]
};

// ─── Context Helpers ────────────────────────────────────────────────────────

/**
 * Extract a comma-separated string of skill names from a career profile.
 * @param {object} career - Career document
 * @returns {string} - Comma-separated skill names (e.g. "Product Strategy, SQL")
 */
function extractSkillNames(career = {}) {
  const skills = (career.skills || []).filter(s => s && s.name).map(s => s.name.trim());
  if (skills.length === 0) return 'your current skills';
  return skills.slice(0, 4).join(', ');
}

/**
 * Generate a salary anchor range based on career profile and target role.
 * Uses experience to scale the anchor; falls back to a generic range.
 * @param {object} career - Career document
 * @param {string} targetRole - User's target role
 * @returns {string} - e.g. "₹30L - 45L" or "a competitive market range"
 */
function getSalaryAnchor(career = {}, targetRole = '') {
  const skills = (career.skills || []).filter(s => s && s.name).map(s => s.name.trim());
  const hasSeniorSkill = skills.some(s => /senior|lead|manage|architect|director/i.test(s));
  const experience = Number(career.experience) || 0;

  let anchorRange = 'a competitive market range';
  if (hasSeniorSkill || experience >= 6) {
    anchorRange = '₹40L - 55L';
  } else if (experience >= 3) {
    anchorRange = '₹30L - 45L';
  } else if (experience >= 1) {
    anchorRange = '₹20L - 30L';
  } else if (targetRole) {
    anchorRange = '₹18L - 28L';
  }
  return anchorRange;
}

function buildContext(user = {}, career = {}, wellness = {}) {
  const cyclePhase = determineCyclePhase(user.cycleData);
  const moods = wellness.moods || [];
  const recentMoods = moods.slice(-3).map(m => m.mood);
  
  return {
    name: user.name ? user.name.split(' ')[0] : 'there',
    currentRole: user.currentRole || 'your current role',
    targetRole: user.targetRole || 'your target role',
    skillNames: extractSkillNames(career),
    salaryAnchor: getSalaryAnchor(career, user.targetRole),
    cyclePhase,
    recentMoods,
    wellnessStreak: wellness.streak || 0,
    careerProgress: career.skills && career.skills.length 
      ? Math.round(career.skills.reduce((a, s) => a + s.level, 0) / career.skills.length)
      : 0
  };
}

function fillTemplate(template, ctx) {
  return template
    .replace(/\{name\}/g, ctx.name)
    .replace(/\{current_role\}/g, ctx.currentRole)
    .replace(/\{target_role\}/g, ctx.targetRole)
    .replace(/\{skill_names\}/g, ctx.skillNames)
    .replace(/\{salary_note\}/g, ctx.targetRole === 'your target role' ? 'negotiating' : `negotiating for ${ctx.targetRole}`)
    .replace(/\{anchor_range\}/g, ctx.salaryAnchor)
    .replace(/\{cycle_phase\}/g, ctx.cyclePhase);
}

/**
 * Word-boundary keyword matcher.
 * Prevents false positives like 'hi' matching inside 'thing' or 'ty' inside 'productivity'.
 * @param {string} text - Lowercased user message
 * @param {string} keyword - Keyword to search for
 * @returns {boolean} - true if the keyword appears as a whole word/phrase
 */
function matchesKeyword(text, keyword) {
  const escaped = String(keyword).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  try {
    return new RegExp(`\\b${escaped}\\b`, 'i').test(text);
  } catch (e) {
    return text.includes(keyword);
  }
}

function classifyIntent(message) {
  const normalizedMessage = String(message || '').toLowerCase();
  const greetingOnly = /^(hi+|hello+|hey+|hiya|yo|hii|good (morning|afternoon|evening))(\s|[!?.-])*$/i.test(normalizedMessage.trim());

  if (greetingOnly) {
    return {
      intent: 'greeting',
      category: 'general',
      confidence: 0.9
    };
  }

let bestMatch = INTENTS.GENERAL;
  let bestScore = 0;

  for (const intent of Object.values(INTENTS)) {
    let score = 0;

    for (const keyword of intent.keywords.high) {
      if (matchesKeyword(normalizedMessage, keyword)) score += 3;
    }

    for (const keyword of intent.keywords.medium) {
      if (matchesKeyword(normalizedMessage, keyword)) score += 2;
    }

    for (const keyword of intent.keywords.low) {
      if (matchesKeyword(normalizedMessage, keyword)) score += 1;
    }

    if (score > bestScore) {
      bestScore = score;
      bestMatch = intent;
    }
  }

  return {
    intent: bestMatch.name,
    category: bestMatch.category,
    confidence: Math.min(1, bestScore / 6)
  };
}

function determineCyclePhase(cycleData = {}) {
  const lastPeriodDate = cycleData.lastPeriodDate ? new Date(cycleData.lastPeriodDate) : null;
  const cycleLength = Number(cycleData.cycleLength) || 28;
  const periodLength = Number(cycleData.periodLength) || 5;

  if (!lastPeriodDate || Number.isNaN(lastPeriodDate.getTime())) {
    return 'unknown';
  }

  const daysSinceLastPeriod = Math.floor((Date.now() - lastPeriodDate.getTime()) / 86400000);
  if (daysSinceLastPeriod < 0) {
    return 'unknown';
  }

  const dayInCycle = daysSinceLastPeriod % cycleLength;

  if (dayInCycle < periodLength) return 'menstrual';
  if (dayInCycle < 13) return 'follicular';
  if (dayInCycle < 15) return 'ovulation';
  return 'luteal';
}

// Sentiment detection for emotional acknowledgment
function detectEmotion(message) {
  const text = String(message || '').toLowerCase();
  const positiveWords = ['happy', 'excited', 'grateful', 'glad', 'great', 'awesome', 'amazing', 'good news', 'promoted', 'love it', 'feeling good', 'wonderful', 'proud'];
  const negativeWords = ['sad', 'stressed', 'anxious', 'worried', 'tired', 'exhausted', 'overwhelmed', 'frustrated', 'angry', 'scared', 'fear', 'burnout', 'crying', 'upset', 'hurt', 'depressed', 'lonely', 'hopeless'];

  let posCount = 0;
  let negCount = 0;

  for (const w of positiveWords) if (text.includes(w)) posCount++;
  for (const w of negativeWords) if (text.includes(w)) negCount++;

  if (negCount > 0 && negCount >= posCount) return 'negative';
  if (posCount > 0 && posCount >= negCount) return 'positive';
  return 'neutral';
}

const EMOTIONAL_ACK = {
  negative: {
    prefix: "I can hear that this is weighing on you, and that's completely valid. 💜 ",
    suffix: "\n\nYou're not alone in this — I'm here with you every step of the way."
  },
  positive: {
    prefix: "That's wonderful to hear — I love this energy! ✨ ",
    suffix: "\n\nCelebrate these wins, {name} — you've earned them!"
  },
  neutral: { prefix: '', suffix: '' }
};

// Follow-up questions per intent so the conversation keeps flowing naturally
const FOLLOW_UPS = {
  salary_negotiation: "Want me to draft a script you can use in your next conversation?",
  interview_prep: "Which part should we start with — behavioral questions, case prep, or a full mock interview?",
  burnout: "Would you like to try a quick breathing exercise together, or talk through what's draining you most?",
  imposter: "What's one thing you've achieved recently that you're proud of?",
  cycle_aware: "Would you like me to plan your next week around your cycle?",
  resume: "Want me to review a resume section, or help you write a specific bullet point?",
  career_growth: "What's your current role, and where do you see yourself in 2 years?",
  work_life_balance: "Which boundary feels most important to set first?",
  networking: "Want to draft your first outreach message together?",
  confidence: "What's one situation where you'd love to feel more confident?",
  career_change: "What field are you thinking about moving into?",
  workplace_issues: "Would you like to plan specific next steps for this situation?",
  public_speaking: "What kind of speaking situation are you preparing for?",
  goal_setting: "What's the one goal you're most excited about right now?",
  motivation: "What's one tiny step you can take in the next 10 minutes?",
  emotional_support: "Would you like to talk more about what's on your mind?",
  how_are_you: "So, how are you feeling today — genuinely?",
  thanks: "Is there anything else you'd like to explore today?",
  small_talk: "What would you like to focus on — career, wellness, or just a chat?",
  joke: "Want to hear another, or should we dive into something helpful?",
  greeting: "What would you like to focus on today — career, wellness, or both?",
  general: "Could you tell me a little more about what's on your mind?"
};

// ─── Knowledge Base (answers many common questions without an LLM) ──────────

const KNOWLEDGE_BASE = [
  {
    topic: 'definition_ai',
    keywords: ['what is ai', 'what is artificial intelligence', 'define ai', 'meaning of ai', 'what are ai'],
    answer: '**AI (Artificial Intelligence)** is technology that lets machines learn from data and perform tasks that normally need human intelligence — like understanding language, recognizing images, making decisions, and predicting outcomes.\n\nIt powers tools like chatbots, recommendation engines, and career-matching platforms. For your career, understanding AI is a huge advantage — roles like AI Product Manager, ML Engineer, and AI Consultant are growing fast.\n\nWant me to suggest AI skills to learn based on your profile? 🚀'
  },
  {
    topic: 'definition_ml',
    keywords: ['what is machine learning', 'what is ml', 'define machine learning', 'what is deep learning'],
    answer: '**Machine Learning (ML)** is a branch of AI where computers learn patterns from data without being explicitly programmed. Instead of hard-coded rules, the model discovers patterns — e.g., predicting which candidates fit a role, or which skill to learn next.\n\n**Key types:**\n• Supervised learning (labeled data)\n• Unsupervised learning (finding patterns)\n• Reinforcement learning (learning by trial & error)\n\nWant to know how to start learning ML for your career? 🤖'
  },
  {
    topic: 'definition_neural_network',
    keywords: ['what is a neural network', 'what are neural networks', 'neural network meaning'],
    answer: 'A **neural network** is a computing system inspired by the human brain — made of layers of connected "neurons" that process information. It learns by adjusting the strength of connections based on data.\n\nIt powers image recognition, speech, translation, and modern AI assistants. If you are exploring a tech/ML career, this is core knowledge!\n\nWant a beginner roadmap to understand neural networks? 🧠'
  },
  {
    topic: 'career_skills_leadership',
    keywords: ['skills for leadership', 'leadership skills', 'become a leader', 'how to be a leader', 'leadership qualities'],
    answer: 'Great leadership comes from a mix of skills:\n\n• **Communication** — clear, honest, and inspiring\n• **Emotional intelligence** — empathy, self-awareness, reading the room\n• **Decision-making** — acting with imperfect information\n• **Delegation** — trusting others, not micromanaging\n• **Vision** — connecting daily work to a bigger goal\n\nPractical tip: start leading *without* a title — volunteer for a project, mentor a teammate, and advocate for your team. Leadership is a behavior, not a position. 💜\n\nWant a personalized leadership growth plan?'
  },
  {
    topic: 'product_manager',
keywords: ['how to become a product manager', 'product manager', 'product management', 'pm role', 'what does a product manager do', 'become a pm', 'product owner'],
    answer: 'A **Product Manager (PM)** owns the "what" and "why" of a product — they decide what to build and why, while engineering figures out the "how".\n\nTo break into PM:\n1. **Understand users** — practice with user interviews and market research\n2. **Learn the toolkit** — PRDs, roadmaps, metrics (DAU, retention, NPS)\n3. **Build a portfolio** — ship a small product or write case studies\n4. **Get visible** — take on PM-adjacent work in your current role\n\nPopular PM paths: Associate PM → PM → Senior PM → Director of Product. Want a mock PM interview question? 🎯'
  },
  {
    topic: 'data_science',
    keywords: ['data science', 'data scientist', 'learn data science', 'data science career'],
    answer: '**Data Science** combines statistics, coding, and business thinking to turn raw data into decisions. Core skills:\n\n• **Statistics & probability**\n• **Python** (pandas, numpy, scikit-learn)\n• **SQL** for data extraction\n• **Data visualization** (Tableau, matplotlib)\n• **Storytelling** with data\n\nEntry path: Data Analyst → Data Scientist → ML Engineer. A great first project: analyze a public dataset and share your findings on LinkedIn. Want help picking a learning path? 📊'
  },
  {
    topic: 'software_engineering',
    keywords: ['software engineer', 'software developer', 'learn to code', 'coding career', 'become a developer'],
    answer: 'Software engineering is one of the most flexible careers — you can work in fintech, healthtech, gaming, or AI. Core skills:\n\n• **Programming languages** — Python, JavaScript, Java, Go\n• **Data structures & algorithms** — for interviews\n• **Version control** — Git/GitHub\n• **Databases & APIs**\n\nStart with one language (Python or JavaScript), build small projects, then a portfolio. For interviews, practice LeetCode-style problems. Want a study plan tailored to your experience? 💻'
  },
  {
    topic: 'career_change',
    keywords: ['how to change career', 'switch careers', 'career transition', 'change my career'],
    answer: 'Great — career changes are more common than you think and often the best decision! Here is a practical roadmap:\n\n1. **Self-assessment** — list what energizes you in your current role and what drains you\n2. **Research** — talk to 3-5 people in your target field (informational interviews)\n3. **Bridge skills** — identify transferable skills and gaps\n4. **Try it out** — freelance, shadow, or take a small project\n5. **Make the leap** — update your resume/LinkedIn and network\n\nWhat field are you considering? I can help make it specific. 🚀'
  },
  {
    topic: 'workplace_relationships',
    keywords: ['how to deal with difficult boss', 'toxic boss', 'bad manager', 'office politics', 'difficult coworker'],
    answer: 'Difficult workplace relationships are stressful — let me help you navigate:\n\n• **Document everything** — dates, what was said, outcomes\n• **Stay professional** — don\'t feed the drama; keep your responses calm and factual\n• **Set boundaries** — communicate what you need clearly and kindly\n• **Find allies** — a trusted colleague or mentor for perspective\n• **Know your options** — HR, internal transfers, or planning an exit\n\nYour well-being matters most. Would you like to role-play a specific conversation? 💜'
  },
  {
    topic: 'work_life_balance_how',
    keywords: ['how to balance work and life', 'how to achieve work life balance', 'work life balance tips', 'manage work and life'],
    answer: 'Work-life balance is really about **intentional energy allocation**, not perfect splits. Try these:\n\n1. **Set boundaries** — decide when work "ends" and protect it\n2. **Time-block** — schedule deep work AND rest deliberately\n3. **Learn to say no** — gracefully decline what doesn\'t serve you\n4. **Digital hygiene** — turn off notifications after hours\n5. **Recharge rituals** — move, sleep, and do something for joy\n\nStart small: one boundary this week. Which one feels most important? ⚖️'
  },
  {
    topic: 'resume_how',
    keywords: ['how to write a resume', 'resume tips', 'make a good resume', 'resume format', 'cv writing'],
    answer: 'Here is a resume that gets noticed:\n\n• **Quantify results** — "grew revenue 40%" beats "led projects"\n• **Use action verbs** — launched, scaled, negotiated, transformed\n• **Tailor per job** — mirror keywords from the description\n• **Keep it clean** — 1 page under 10 years experience, standard headers (ATS-friendly)\n• **Front-load impact** — your best achievement first in each role\n\nWant me to help you strengthen a specific bullet point or section? 💼'
  },
  {
    topic: 'interview_questions_how',
    keywords: ['how to answer interview questions', 'interview questions', 'tell me about yourself', 'common interview questions'],
    answer: 'The most common interview question is **"Tell me about yourself"** — here\'s a winning structure:\n\n• **Past** → a 1-line summary of your background\n• **Present** → your current role and what you do\n• **Future** → why you want THIS role and what you bring\n\nFor behavioral questions, use **STAR**: Situation, Task, Action, Result.\n\nWant me to run a rapid-fire mock interview with you right now? 🎯'
  },
  {
    topic: 'salary_how',
    keywords: ['how much should i be paid', 'what salary should i ask', 'salary range', 'how to negotiate salary', 'fair salary'],
    answer: 'Here is how to find and negotiate a fair salary:\n\n1. **Research** — use Glassdoor, LinkedIn Salary, and Levels.fyi for your role + location + years\n2. **Know your number** — set a minimum (walk-away) and a target\n3. **Anchor high** — state a range 10-15% above your minimum\n4. **Quantify your value** — bring 3 measurable wins\n5. **Never accept the first offer** — always counter at least once\n\nWhat role and experience level are you targeting? I can help you estimate a fair range. 💰'
  },
  {
    topic: 'stress_management',
    keywords: ['how to reduce stress', 'manage stress', 'lower stress', 'anxiety at work', 'how to calm down'],
    answer: 'Here are techniques that actually work for stress:\n\n• **Breathe** — try 4-7-8: inhale 4s, hold 7s, exhale 8s (calms the nervous system)\n• **Move** — a 10-minute walk shifts stress hormones\n• **Prioritize** — cut your list to 3 things today\n• **Boundaries** — say no to non-essentials\n• **Talk** — name how you feel; it reduces its power\n\nWant to do a quick guided breathing exercise together? 💜'
  },
  {
topic: 'sleep_wellness',
    keywords: ['how to sleep better', 'improve sleep', 'insomnia', 'can\'t sleep', 'sleep tips', 'sleep important', 'why sleep', 'sleep for productivity'],
    answer: 'Better sleep transforms your energy and focus. Try:\n\n• **Consistent schedule** — same wake time daily (even weekends)\n• **Wind-down ritual** — screens off 45 min before bed\n• **Cool, dark room** — ideal temp ~18-20°C\n• **Limit caffeine** — none after early afternoon\n• **Move daily** — exercise improves sleep quality\n\nSleep is a performance tool, not a luxury. When is your current bedtime? 🌙'
  },
  {
    topic: 'confidence_how',
    keywords: ['how to be more confident', 'build confidence', 'gain confidence', 'boost self esteem', 'feel confident'],
    answer: 'Confidence is built through action, not waiting to "feel" ready:\n\n1. **Small wins** — set and achieve one tiny goal daily\n2. **Preparation** — you feel confident when you are prepared\n3. **Body language** — posture, eye contact, voice ("act as if")\n4. **Mindset** — swap "I hope" for "I am"\n5. **Stop comparing** — you\'re comparing your chapter 1 to someone\'s chapter 20\n\nWhat specific situation do you want to feel confident in? Let\'s tackle it. 🌟'
  },
  {
    topic: 'networking_how',
    keywords: ['how to network', 'networking tips', 'build professional network', 'linkedin networking', 'make connections'],
    answer: 'Networking is about genuine relationships, not collecting contacts:\n\n• **Give first** — share resources and introductions before asking\n• **Be specific** — "I\'d love to learn about your path to X" beats "Can we connect?"\n• **Follow up** — personalized note within 24 hours\n• **Nurture** — check in every 60-90 days\n\nThis week: reach out to 1 person you admire with a genuine compliment + question. Want me to draft that message? 🤝'
  },
  {
    topic: 'promotion_how',
    keywords: ['how to get a promotion', 'get promoted', 'ask for promotion', 'promotion strategy', 'climb the ladder'],
    answer: 'Getting promoted is about visibility + evidence + the ask:\n\n1. **Know the criteria** — what does the next level actually require?\n2. **Document wins** — track weekly so you don\'t forget by review time\n3. **Get visible** — present to leadership, own high-impact projects\n4. **Find a champion** — someone who advocates for you\n5. **Make the ask** — present your case with evidence, not just desire\n\nWhat role do you want to reach, and what\'s your current one? 💪'
  },
  {
    topic: 'learning_skills',
    keywords: ['what skills should i learn', 'best skills to learn', 'future skills', 'in demand skills', 'skills for career'],
    answer: 'Some of the most in-demand skills right now:\n\n• **Digital/tech** — AI, data literacy, SQL, Python, cybersecurity\n• **Human** — communication, emotional intelligence, leadership, adaptability\n• **Business** — product thinking, negotiation, project management\n\nA smart mix: 1 technical skill + 1 human skill. Match them to your target role for maximum impact.\n\nWhat role are you aiming for? I\'ll suggest the perfect skill combo. 🎯'
  },
  {
    topic: 'mentorship',
    keywords: ['how to find a mentor', 'mentor', 'mentorship', 'find a mentor'],
    answer: 'A great mentor can accelerate your career enormously. Here\'s how to find one:\n\n• **Look nearby** — senior colleagues, managers, or alumni\n• **Be specific** — ask for advice on a *specific* thing, not general guidance\n• **Offer value** — good mentoring is reciprocal\n• **Start small** — a 30-min coffee chat, not a formal arrangement\n• **Use platforms** — LinkedIn, ADPList, or company mentorship programs\n\nWhat area of your career most needs a mentor right now? 🌱'
  },
  {
    topic: 'burnout_prevention',
    keywords: ['how to prevent burnout', 'avoid burnout', 'burnout prevention', 'stop feeling exhausted'],
    answer: 'Preventing burnout is about protecting your energy before it runs out:\n\n• **Boundaries** — protect personal time like a meeting\n• **Realistic workload** — flag overcommitment early\n• **Recovery** — build rest INTO your week, not just on weekends\n• **Meaning** — reconnect with what your work is for\n• **Support** — don\'t carry it alone; talk to someone\n\nWhat\'s the biggest energy-drain in your week right now? 💜'
  },
  {
    topic: 'career_goals',
    keywords: ['how to set career goals', 'set career goals', 'career plan', 'plan my career', 'career roadmap'],
    answer: 'Here\'s a simple system to set and reach career goals:\n\n1. **Pick ONE priority goal** — focus beats multitasking\n2. **Make it SMART** — Specific, Measurable, Achievable, Relevant, Time-bound\n3. **Break into weekly milestones** — big goals are just small steps stacked\n4. **Track & celebrate** — every step counts\n5. **Review monthly** — adjust as you learn\n\nWhat\'s the goal you\'re most excited about? Let\'s make it concrete. 🎯'
  }
];

// ─── Open-Question Fallback ─────────────────────────────────────────────────

const QUESTION_TOPICS = [
  {
    label: 'career',
    keywords: ['job', 'career', 'role', 'work', 'promotion', 'interview', 'resume', 'salary', 'skills', 'manager', 'lead', 'field', 'industry', 'professional', 'grow', 'goal']
  },
  {
    label: 'wellness',
    keywords: ['stress', 'anxiety', 'burnout', 'sleep', 'mood', 'energy', 'balance', 'boundary', 'rest', 'self-care', 'self care', 'mind', 'health', 'feel', 'tired', 'overwhelmed']
  },
  {
    label: 'tech',
    keywords: ['ai', 'machine learning', 'coding', 'software', 'python', 'data', 'programming', 'technology', 'computer', 'developer', 'app', 'website', 'database']
  },
  {
    label: 'learning',
    keywords: ['learn', 'study', 'course', 'skill', 'education', 'degree', 'certification', 'university', 'train', 'knowledge']
  },
  {
    label: 'money',
    keywords: ['money', 'salary', 'pay', 'income', 'earning', 'raise', 'finance', 'budget', 'invest', 'save']
  }
];

const OPEN_QUESTION_TEMPLATES = {
  career: [
    "That's a great question about your career. Here's the honest, practical take:\n\n1. **Clarify your goal** — what outcome do you actually want in the next 6-12 months?\n2. **Build the evidence** — collect achievements and quantify your impact\n3. **Get visible** — share your work with leadership and peers\n4. **Invest in skills** — choose the 1-2 skills that close the gap to your target role\n\nWant me to go deeper on any of these steps for your specific situation? 💼",
    "Let's break that down for your career. The key is to turn it into an action plan:\n\n• **Assess where you are** — strengths, gaps, and what energizes you\n• **Define your target** — a specific role or level you want\n• **Map the gap** — what separates you from that goal\n• **Act weekly** — one focused step every week compounds fast\n\nWhich part of your career do you want to focus on first? 🎯"
  ],
  wellness: [
    "I hear you — and your well-being matters. Here's a supportive starting point:\n\n• **Name the feeling** — getting specific reduces its power\n• **Protect your energy** — set one boundary today\n• **Breath & body** — a short walk or 5 deep breaths resets your nervous system\n• **Reach out** — you don't have to carry it alone\n\nHow are you feeling right now, honestly? I'm here with you. 💜",
    "Thank you for sharing that. For your wellness, small consistent steps work best:\n\n1. **Check-in daily** — a 2-minute mood check\n2. **Rest deliberately** — schedule downtime, not just leftovers\n3. **Move gently** — movement shifts mood and energy\n4. **Talk it out** — naming what's heavy lightens it\n\nWhat's one thing that would help you feel better today? 🌸"
  ],
  tech: [
    "Great technical question! Here's a solid way to approach it:\n\n• **Start with the fundamentals** — the core concept before the tools\n• **Practice by building** — small projects teach more than tutorials\n• **Understand the 'why'** — not just the syntax\n• **Keep it current** — tech moves fast, follow good sources\n\nWhat specific technology are you exploring? I can guide you from there. 💻",
    "Let's dig into the tech side. A practical framework:\n\n1. **Define the goal** — what do you want to build or learn?\n2. **Break it down** — split into small, achievable pieces\n3. **Learn by doing** — apply concepts immediately\n4. **Get feedback** — share your work and iterate\n\nTell me more about what you're trying to do — is it for a project, a job, or curiosity? 🚀"
  ],
  learning: [
    "Learning is a superpower — here's how to make it stick:\n\n• **Set a clear goal** — learn something specific, not 'everything'\n• **Use active recall** — practice and test yourself, not just re-read\n• **Spaced repetition** — review at intervals to remember long-term\n• **Apply it** — use what you learn in a real project\n\nWhat subject are you interested in learning? I'll help you design a plan. 📚",
    "Love that you're investing in learning! The best approach:\n\n1. **Pick one skill** to focus on (avoid spreading thin)\n2. **Find one good resource** — a course, book, or mentor\n3. **Schedule it** — 30 focused minutes daily beats 3 hours weekly\n4. **Share it** — teaching others deepens your own understanding\n\nWhat do you want to learn, and how much time can you commit weekly? ✨"
  ],
  money: [
    "Good question about money — let's think about it practically:\n\n• **Know your numbers** — research market rates for your role and area\n• **Understand your value** — quantify your impact to negotiate from strength\n• **Build good habits** — track spending, save first, invest wisely\n• **Plan for growth** — salary is one part; skills and leverage matter too\n\nWhat would you like to focus on — earning more, budgeting, or investing? 💰"
  ],
  general: [
    "That's a thoughtful question. Here's my take:\n\n• **Break it down** — separate the key parts of what you're asking\n• **Consider the goal** — what would a good outcome look like?\n• **Take one step** — act on the most important part first\n• **Stay curious** — keep refining as you learn\n\nTell me a little more about the context — is this about your career, wellness, or something else? I'm here to help. 💜",
    "I'd love to help with that. Let me give you a practical starting point:\n\n1. Look at the core of the question — what's really being asked?\n2. Identify what you can control and act on that\n3. Seek input from people who've done it before\n4. Iterate — you don't need it perfect, just started\n\nWhat's the situation behind this question? That'll help me tailor a better answer. ✨"
  ]
};

function detectQuestionTopic(message) {
  const text = String(message || '').toLowerCase();
  const isQuestion = /(\?|what|how|why|when|where|who|can you|tell me|explain|help me)/i.test(text);
  if (!isQuestion) return null;

  let bestTopic = 'general';
  let bestScore = 0;
  for (const topic of QUESTION_TOPICS) {
    let score = 0;
    for (const kw of topic.keywords) {
      if (text.includes(kw)) score += 1;
    }
    if (score > bestScore) {
      bestScore = score;
      bestTopic = topic.label;
    }
  }
  return bestTopic;
}

function findKnowledgeBaseAnswer(message) {
  const text = String(message || '').toLowerCase().trim();
  for (const item of KNOWLEDGE_BASE) {
    for (const kw of item.keywords) {
      const trimmedKw = String(kw || '').trim();
      if (!trimmedKw) continue;
      if (matchesKeyword(text, trimmedKw)) {
        return item;
      }
    }
  }
  return null;
}

// ─── Short Conversational Replies ───────────────────────────────────────────
// When the user sends a very short acknowledgment ("good", "no", "ok", "yes",
// "nice", "fine", etc.) we give a varied, contextual, HUMAN-sounding reply
// instead of routing to the generic "general" template (which used to repeat).
const SHORT_POSITIVE_REPLIES = [
  "That makes me happy to hear! 😊 What else has been going on with you today?",
  "Love that! Positive energy is contagious. So what would you like to focus on — career, wellness, or both?",
  "Glad to hear it! ✨ Got anything exciting coming up that you'd like to talk about?",
  "That's great — I love when things are going well. What's one thing that made it good today?",
  "Awesome! 🙌 If there's anything you want to build on from that, I'm all ears."
];

const SHORT_NEGATIVE_REPLIES = [
  "No worries at all — totally okay. 💜 What's on your mind? I'm here for whatever you need.",
  "Alright, no pressure. If there's something bothering you, I'm a safe space to talk it through.",
  "Understandable. We don't have to dive into anything — but if you'd like to chat, I'm right here.",
  "Got it. Sometimes it's nice to just take a pause. Is there anything you'd like to talk about?",
  "That's fine — we can keep it light! Want to hear a quick tip, or just take a gentle pause?"
];

const SHORT_NEUTRAL_REPLIES = [
  "Okay! 😊 What would you like to chat about today?",
  "Sure thing. I'm here for career talks, wellness check-ins, or just a friendly conversation.",
  "Got it! Whenever you're ready, I can help with interview prep, salary tips, stress relief, and more.",
  "Perfect. So — what's one thing I can help you with today?",
  "Noted! I'm all ears whenever you're ready to share or explore something."
];

// Categorize short, single-intent conversational replies.
function getShortReplyCategory(message) {
  const text = String(message || '').trim().toLowerCase();
  if (!text || text.length > 12) return null;

  const positive = ['good', 'great', 'fine', 'nice', 'awesome', 'amazing', 'cool', 'ok', 'okay', 'yes', 'yep', 'yeah', 'sure', 'love', 'happy', 'glad', 'well', 'better', 'perfect', 'excellent', 'fantastic', 'super', 'true', 'right', 'correct', 'alright'];
  const negative = ['no', 'nope', 'nah', 'not good', 'bad', 'sad', 'tired', 'meh', 'not really', 'not great', 'ugh', 'awful', 'terrible', 'worse', 'not ok', 'not okay', 'nothing'];

  if (positive.includes(text)) return 'positive';
  if (negative.includes(text)) return 'negative';
  return null;
}

// ─── Public API ─────────────────────────────────────────────────────────────

/**
 * Generate AI response for chat message
 * @param {string} message - User message
 * @param {object} context - { user, career, wellness }
 * @returns {object} - { response, category, intent, confidence }
 */
function generateAIResponse(message, context = {}) {
  const { user = {}, career = {}, wellness = {} } = context;
  const ctx = buildContext(user, career, wellness);
const { intent, category, confidence } = classifyIntent(message);

  // 0. Short conversational acknowledgment — give a varied, HUMAN reply
  //    instead of the generic "general" template (which used to repeat).
  const shortCat = getShortReplyCategory(message);
  if (shortCat) {
    const pool = shortCat === 'positive' ? SHORT_POSITIVE_REPLIES
      : shortCat === 'negative' ? SHORT_NEGATIVE_REPLIES
      : SHORT_NEUTRAL_REPLIES;
    const hash = String(message).split('').reduce((a, c) => a + c.charCodeAt(0), 0);
    const response = pool[hash % pool.length].replace(/\{name\}/g, ctx.name);
    return {
      response,
      category,
      intent: 'acknowledgment',
      confidence: 0.9,
      followUp: FOLLOW_UPS.general,
      emotion: detectEmotion(message),
      personalization: { name: ctx.name, cyclePhase: ctx.cyclePhase, careerProgress: ctx.careerProgress }
    };
  }

  // 1. Knowledge base first — direct, factual answers for common questions
  const kbMatch = findKnowledgeBaseAnswer(message);
  if (kbMatch) {
    return {
      response: kbMatch.answer,
      category: 'general',
      intent: kbMatch.topic,
      confidence: 0.95,
      followUp: FOLLOW_UPS.general,
      emotion: detectEmotion(message),
      personalization: {
        name: ctx.name,
        cyclePhase: ctx.cyclePhase,
        careerProgress: ctx.careerProgress
      }
    };
  }

  // 2. Intent templates (deterministic based on message hash for consistency)
  const templates = RESPONSE_TEMPLATES[intent] || RESPONSE_TEMPLATES.general;
  const hash = String(message).split('').reduce((a, c) => a + c.charCodeAt(0), 0);

  let response;

  // 3. Open-question fallback: if no specific intent matched but the user
  //    asked a real question, answer it helpfully by topic (never deflect).
  if (intent === 'general') {
    const topic = detectQuestionTopic(message);
    if (topic && OPEN_QUESTION_TEMPLATES[topic]) {
      const openTemplates = OPEN_QUESTION_TEMPLATES[topic];
      response = fillTemplate(openTemplates[hash % openTemplates.length], ctx);
    } else {
      const template = templates[hash % templates.length];
      response = fillTemplate(template, ctx);
    }
  } else {
    const template = templates[hash % templates.length];
    response = fillTemplate(template, ctx);
  }
  
  // Add cycle awareness when relevant
  if (intent === 'cycle_aware' && ctx.cyclePhase !== 'unknown') {
    const phaseContext = {
      menstrual: 'Since you mentioned your cycle — during your **menstrual phase** right now, energy is naturally lower. Focus on planning, reflection, and self-compassion. 🌸',
      follicular: 'Since you mentioned your cycle — you\'re likely in your **follicular phase**! This is your peak energy window. Ideal for pitching, presenting, and starting new projects. 🚀',
      ovulation: 'Since you mentioned your cycle — you\'re near **ovulation**, when communication and social energy peak. Perfect for networking and important conversations! ✨',
      luteal: 'Since you mentioned your cycle — you\'re in your **luteal phase**. Channel that focus into deep work, organizing, and tying up loose ends. 🔍',
      unknown: ''
    };
    response += '\n\n' + phaseContext[ctx.cyclePhase];
  }

  // Add personalized touch based on career progress
  if (intent === 'career_growth' && ctx.careerProgress >= 80) {
    response += '\n\nYou\'re at **' + ctx.careerProgress + '% career progress** — you\'re so close! Time to focus on leadership visibility and owning your narrative. 🌟';
  }

return {
    response,
    category,
    intent,
    confidence,
    followUp: FOLLOW_UPS[intent] || FOLLOW_UPS.general,
    emotion: detectEmotion(message),
    personalization: {
      name: ctx.name,
      cyclePhase: ctx.cyclePhase,
      careerProgress: ctx.careerProgress
    }
  };
}

/**
 * Generate daily insight for dashboard
 * @param {object} context - { user, career, wellness }
 * @returns {object} - { insight, category, reason }
 */
function generateDailyInsight(context = {}) {
  const { user = {}, career = {}, wellness = {} } = context;
  const ctx = buildContext(user, career, wellness);
  const insights = [];

  // Career-based insight
  if (ctx.careerProgress > 0) {
    if (ctx.careerProgress >= 80) {
      insights.push({
        insight: `You're at ${ctx.careerProgress}% career progress — focus on leadership visibility and stakeholder impact to close the gap. Your ${ctx.skillNames.split(',')[0] || 'core'} skills are ready.`,
        category: 'career',
        reason: 'High progress detected'
      });
    } else if (ctx.careerProgress >= 50) {
      insights.push({
        insight: `Your career progress is ${ctx.careerProgress}% — consistency is key. This week, focus on ${ctx.skillNames.split(',')[1] || 'one key skill'} to accelerate growth.`,
        category: 'career',
        reason: 'Mid-progress optimization'
      });
    } else {
      insights.push({
        insight: `You're building momentum at ${ctx.careerProgress}% career progress. Start with small wins — one skill at a time. I suggest starting with ${ctx.skillNames.split(',')[0] || 'your foundation skills'}.`,
        category: 'career',
        reason: 'Early-stage momentum'
      });
    }
  } else {
    insights.push({
      insight: `Welcome ${ctx.name}! 🌱 Start by adding your current role and 3 key skills to Career AI so I can build your personalized growth roadmap.`,
      category: 'career',
      reason: 'New user onboarding'
    });
  }

  // Wellness-based insight
  if (ctx.wellnessStreak >= 7) {
    insights.push({
      insight: `Amazing — ${ctx.wellnessStreak}-day wellness streak! Your consistency is inspiring. Keep protecting this habit; it's the foundation of all your achievements. 💪`,
      category: 'wellness',
      reason: 'Strong streak detected'
    });
  } else if (ctx.wellnessStreak > 0) {
    insights.push({
      insight: `${ctx.wellnessStreak}-day streak and counting! Logging today keeps the chain alive. Small daily actions compound into extraordinary results. 🌱`,
      category: 'wellness',
      reason: 'Active streak'
    });
  } else {
    insights.push({
      insight: `Start a wellness streak today — log your mood in Wellness and I'll track your patterns to give you personalized insights. It only takes 30 seconds! ✨`,
      category: 'wellness',
      reason: 'No streak yet'
    });
  }

  // Cycle-aware insight
  if (ctx.cyclePhase !== 'unknown') {
    const phaseTips = {
      menstrual: 'Today is ideal for reflection and planning. Light focus work, gentle movement. Your body is asking for rest — listen. 🌸',
      follicular: 'Your energy peaks today! Schedule pitches, presentations, and bold conversations in this window. Seize the momentum! 🚀',
      ovulation: 'Communication superpower day! Perfect for networking, negotiations, and key stakeholder meetings. ✨',
      luteal: 'Deep work day — analytics, documentation, and organization will flow. Save big presentations for next week. 🔍'
    };
    insights.push({
      insight: `Cycle awareness: ${phaseTips[ctx.cyclePhase]}`,
      category: 'wellness',
      reason: `Currently in ${ctx.cyclePhase} phase`
    });
  }

  // Return deterministic insight based on day of year
  const dayOfYear = Math.floor((Date.now() - new Date(new Date().getFullYear(), 0, 0)) / 86400000);
  return insights[dayOfYear % insights.length];
}

/**
 * Predict opportunity match score
 * Simple ML-style scoring based on user profile vs opportunity
 * @param {object} user - User profile
 * @param {object} opportunity - Opportunity document
 * @returns {number} - 0-100 match score
 */
function predictMatchScore(user = {}, opportunity = {}) {
  let score = 50;
  const targetRole = (user.targetRole || '').toLowerCase();
  const title = (opportunity.title || '').toLowerCase();
  const tags = (opportunity.tags || []).join(' ').toLowerCase();

  // Role alignment (+15)
  if (targetRole && title.includes(targetRole)) score += 15;
  else if (targetRole && title.split(' ').some(w => w.length > 3 && targetRole.includes(w))) score += 10;

  // Experience alignment (+10)
  const exp = user.experience || 0;
  if (exp >= 5 && (tags.includes('senior') || tags.includes('lead'))) score += 10;
  else if (exp >= 2 && exp < 5 && tags.includes('mid')) score += 8;

// Skill alignment (+10)
  // Skills may be stored as plain strings OR as { name, level } objects
  // (e.g. after profile sync). Normalize both to lowercase strings.
  const skills = (user.skills || [])
    .map(s => (typeof s === 'string' ? s : (s && s.name) || ''))
    .map(s => s.toLowerCase())
    .filter(s => s);
  if (skills.some(s => tags.includes(s))) score += 10;

  // Remote preference (+10)
  if (user.preferences?.remoteOnly && opportunity.location?.toLowerCase().includes('remote')) score += 10;

  // Tags similarity (+5)
  const userTags = (user.preferences?.jobTypes || []).join(' ').toLowerCase();
  if (userTags && tags && tags.includes(userTags)) score += 5;

  return Math.min(97, Math.max(35, score));
}

module.exports = {
  generateAIResponse,
  generateDailyInsight,
  classifyIntent,
  predictMatchScore,
  determineCyclePhase,
  INTENTS
};