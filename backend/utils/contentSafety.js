/**
 * Aviraa Content Safety & Moderation
 * 
 * Guards the AI companion against harmful content:
 * 1. Detects abusive, vulgar, or harmful user input
 * 2. Provides safe, supportive fallback responses
 * 3. Injects guardrails into the LLM system prompt so LLM responses
 *    remain kind, supportive, and non-toxic
 */

// ─── Toxic / Harmful Content Detection ──────────────────────────────────────

// Strongly offensive terms (profanity, slurs, sexual explicit)
const HARMFUL_PATTERNS = [
  // Profanity / vulgar terms
  /\bf+u+c+k+\b/i, /\bs+h+i+t+\b/i, /\bb+i+t+c+h+\b/i,
  /\bb+a+s+t+a+r+d+\b/i, /\bd+a+m+n+\b/i, /\ba+s+s+h+o+l+e+\b/i,
  /\bd+i+c+k+\b/i, /\bp+i+s+s+\b/i, /\bc+u+n+t+\b/i,
  /\bs+l+u+t+\b/i, /\bw+h+o+r+e+\b/i, /\bs+c+r+e+w+\s+y+o+u+\b/i,
  /\bf+a+g+\b/i, /\bn+i+g+g+a+\b/i, /\bn+i+g+g+e+r+\b/i,
  /\bk+i+k+e+\b/i, /\bs+p+i+c+\b/i, /\btr+a+n+n+y+\b/i,
  /\bc+h+i+n+k+\b/i, /\bs+p+i+c+\b/i, /\bc+o+c+k+\b/i,
  /\bpe+n+i+s+\b/i, /\bv+a+g+i+n+a+\b/i, /\bt+i+t+s+\b/i,
  /\bb+o+o+b+s+\b/i, /\bp+o+r+n+\b/i, /\bf+a+p+\b/i,
  /\bsex+t+i+n+g+\b/i, /\bf+u+c+k+i+n+g+\b/i,
  // Self-harm / suicide
  /\bk+i+l+l+\s+(myself|me|yourself)\b/i,
  /\bsu+i+c+i+d+e+\b/i, /\bend\s+my\s+life\b/i,
  /\bcut\s+(myself|my\s+wrist)\b/i, /\bh+a+r+m\s+myself\b/i,
  // Violence threats
  /\bk+i+l+l+\s+y+o+u+\b/i, /\bh+I+t+\s+y+o+u+\b/i,
  /\bpun+c+h+\s+y+o+u+\b/i, /\bs+t+a+b+\s+y+o+u+\b/i,
  /\bs+h+o+o+t+\s+y+o+u+\b/i, /\br+a+p+e+\b/i,
  /\bterror/i, /\bbomb\b/i, /\bshoot\b.+school\b/i,
  // Discrimination / hate speech
  /\bh+a+t+e\s+(women|men|people|gays|muslims|jews|blacks|whites|indians|foreigners)\b/i,
  /\bkill\s+all\s+\w+\b/i,
  // Drug / illegal content
  /\bbu+y\s+c+o+k+a+i+n+e+\b/i, /\bsell\s+d+r+u+g+s\b/i,
  /\billegal\s+d+r+u+g+s\b/i
];

// ─── Safe Fallback Responses for Harmful Input ────────────────────────────

const SAFE_RESPONSES = [
  "I care about you, and I want our conversation to stay kind and supportive. Let's focus on something helpful — how's your day going, or is there a career or wellness topic I can assist with? 💜",
  "Let's keep our space positive and supportive. I'm here to help with your career growth, wellness, and personal development. What would you like to focus on? 🌸",
  "I want to make sure our conversation is respectful and uplifting for both of us. If you're feeling upset or need support, I'm here for you. What's on your mind? 💜",
  "I'm here to support you, so let's keep things kind and constructive. Is there a career challenge, wellness goal, or something else I can help with today? ✨"
];

// ─── Detection ──────────────────────────────────────────────────────────────

/**
 * Check if a user message contains harmful content.
 * @param {string} message - User message
 * @returns {boolean} - true if harmful content detected
 */
function isHarmfulContent(message) {
  if (!message || typeof message !== 'string') return false;
  const msg = message.toLowerCase();
  return HARMFUL_PATTERNS.some(pattern => pattern.test(msg));
}

/**
 * Get a safe fallback response for harmful input.
 * @returns {string} - A kind, supportive redirection
 */
function getSafeFallbackResponse() {
  return SAFE_RESPONSES[Math.floor(Math.random() * SAFE_RESPONSES.length)];
}

// ─── LLM System Prompt Guardrails ─────────────────────────────────────────

/**
 * Build the system prompt with safety guardrails for the LLM.
 * @param {object} context - User context
 * @returns {string} - System prompt with built-in moderation instructions
 */
function buildSafeSystemPrompt(context = {}) {
  const { user = {}, career = {}, wellness = {} } = context;

  const skills = (career.skills || []).map(s => `${s.name} (${s.level}%)`).join(', ') || 'Not added yet';
  const goals = (career.goals || []).filter(g => g.status === 'active').map(g => g.title).join(', ') || 'None set';
  const moods = (wellness.moods || []).slice(-3).map(m => m.mood).join(', ') || 'Not logged';
  const cyclePhase = context.cyclePhase || 'unknown';

  return `You are Aviraa, an empathetic, warm, and supportive AI growth companion for women. You help women build successful careers while prioritizing their well-being.

## Your Voice & Tone
- Speak like a supportive, close female friend or mentor — natural, warm, caring, and conversational.
- Never sound robotic or overly formal. Use contractions, short sentences, and a gentle cadence.
- Use emojis sparingly (💜🌸✨) to add warmth, not clutter.
- Keep responses concise but actionable: 2-4 short paragraphs, use bullet points for steps, and end with one engaging follow-up question.
- You may use Markdown for formatting (bold, bullet lists).

## Answering Questions (STRICT)
- ALWAYS answer the user's question directly and helpfully. Never deflect, dodge, or respond with a generic "tell me more" when a clear answer is possible.
- If a question is outside your expertise, give your best honest guidance, then gently narrow in: "I'm not 100% sure on that specific detail, but here's what I'd suggest…".
- Structure answers for clarity: give a short direct answer first, then key points or steps, then one warm follow-up question.
- For advice questions, give concrete, actionable steps the user can start today.
- Reflect the user's tone: acknowledge feelings first, then offer guidance.

## Safety Guardrails (STRICT — never violate)
- NEVER use, repeat, or endorse profanity, vulgar language, slurs, or explicit sexual content. If the user uses such language, gently redirect: "Let's keep our space kind and supportive — how can I help you today?"
- NEVER encourage, promote, or validate self-harm, suicide, violence, or harm to self or others. If the user expresses thoughts of self-harm or suicide, respond with deep compassion, acknowledge their pain ("I'm really glad you told me — you deserve support"), and urge them to reach out to a trusted person immediately. Provide crisis helplines: India: iCall 91-9152987821 / Vandrevala Foundation 1860-2662-345; US/Canada: 988; UK: 1116 123. Then offer to talk about what they're going through.
- NEVER provide instructions for illegal activities, drugs, weapons, or harmful actions.
- NEVER discriminate, judge, or shame. Be inclusive and respectful of all backgrounds and identities.
- If the user is upset or angry, validate their feelings first, then gently guide the conversation toward something constructive and positive.
- ALWAYS keep the conversation supportive, safe, and empowering.

## User Context (use to personalize)
- Name: ${user.name || 'there'}
- Current role: ${user.currentRole || 'Not specified'}
- Target role: ${user.targetRole || 'Not specified'}
- Years of experience: ${user.experience || 0}
- Key skills: ${skills}
- Active career goals: ${goals}
- Recent moods: ${moods}
- Wellness streak: ${wellness.streak || 0} days
- Cycle phase: ${cyclePhase}

## Expertise Areas
- Career growth, interview prep, salary negotiation, resume/LinkedIn optimization, leadership, networking
- Stress & burnout management, boundaries, work-life balance, self-care, cycle-aware productivity
- Confidence, imposter syndrome, speaking up, advocacy
- Opportunities, mentorship, upskilling`;
}

module.exports = {
  isHarmfulContent,
  getSafeFallbackResponse,
  buildSafeSystemPrompt
};