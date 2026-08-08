// ============ COMPANION CHAT ============

let currentSessionId = null;

// ============ CONVERSATION STATE ============
const conversationState = {
  messages: [],
  context: {
    userName: 'there',
    currentRole: 'your current role',
    targetRole: 'your target role',
    cyclePhase: 'unknown',
    stressLevel: 'Moderate'
  }
};

// Load user context from localStorage
function loadUserContext() {
  const cached = api.getUser();
  if (cached) {
    const firstName = (cached.name || 'there').split(' ')[0];
    conversationState.context.userName = firstName;
    conversationState.context.currentRole = cached.currentRole || 'your current role';
    conversationState.context.targetRole = cached.targetRole || 'your target role';
  }
  return cached;
}

async function startSession() {
  try {
    // Try to resume the most recent active session first
    const data = await api.get('/chat/session');
    currentSessionId = data.sessionId;
    console.log('💬 Chat session resumed:', currentSessionId);
    return data;
  } catch (error) {
    console.warn('Using local chat mode (no API session):', error.message);
    currentSessionId = 'local_session_' + Date.now();
    return null;
  }
}

// Load persisted message history from the backend into the chat UI
async function loadHistory() {
  try {
    const data = await api.get('/chat/session');
    if (!data || !data.sessionId) return;

    currentSessionId = data.sessionId;
    const messages = data.messages || [];

    const container = document.getElementById('chatMessages');
    if (!container) return;

    // Clear the static welcome message, then render persisted history
    container.innerHTML = '';

    if (messages.length === 0) {
      addMessage("Hi there! I'm your Aviraa companion. I'm here to support both your career ambitions and personal well-being. 💜 What's on your mind today?", 'bot');
      return;
    }

    messages.forEach(m => {
      const sender = m.role === 'user' ? 'user' : 'bot';
      addMessage(m.content, sender);
    });

    // Populate recent conversations list
    renderRecentConversations();
  } catch (error) {
    console.warn('Could not load chat history:', error.message);
  }
}

// Render the list of past conversations dynamically
async function renderRecentConversations() {
  try {
    const chats = await api.get('/chat/history');
    const recentList = document.getElementById('recentList');
    if (!recentList) return;

    const activeChats = chats.filter(c => c.isActive !== false);

    if (activeChats.length === 0) {
      recentList.innerHTML = `<div class="recent-item"><i class="fas fa-comment"></i><span>No conversations yet</span></div>`;
      return;
    }

    recentList.innerHTML = activeChats.map(c => {
      const firstMsg = (c.messages || []).find(m => m.role === 'user');
      const preview = firstMsg ? firstMsg.content.slice(0, 40) : 'New conversation';
      const date = c.sessionStart ? new Date(c.sessionStart).toLocaleDateString() : '';
      return `
        <div class="recent-item" data-session="${c._id}" onclick="resumeConversation('${c._id}')">
          <i class="fas fa-comment"></i>
          <span>${escapeHtml(preview)}</span>
          <button class="recent-delete" onclick="event.stopPropagation(); deleteConversation('${c._id}')" title="Delete conversation">
            <i class="fas fa-trash-alt"></i>
          </button>
        </div>
      `;
    }).join('');
  } catch (error) {
    console.warn('Could not load recent conversations:', error.message);
  }
}

// Resume a specific past conversation by loading its messages
async function resumeConversation(sessionId) {
  try {
    const chats = await api.get('/chat/history');
    const chat = chats.find(c => String(c._id) === String(sessionId));
    if (!chat) return;

    currentSessionId = String(chat._id);
    const container = document.getElementById('chatMessages');
    if (container) container.innerHTML = '';

    const messages = chat.messages || [];
    if (messages.length === 0) {
      addMessage("Hi again! I'm here for you. What would you like to talk about? 💜", 'bot');
      return;
    }

    messages.forEach(m => {
      const sender = m.role === 'user' ? 'user' : 'bot';
      addMessage(m.content, sender);
    });
  } catch (error) {
    console.warn('Could not resume conversation:', error.message);
  }
}

// Permanently delete a conversation
async function deleteConversation(sessionId) {
  if (!confirm('Delete this conversation permanently?')) return;

  try {
    await api.delete(`/chat/session/${sessionId}`);
    showToast('🗑️ Conversation deleted');

    // If we deleted the current session, start fresh
    if (String(currentSessionId) === String(sessionId)) {
      currentSessionId = null;
      const container = document.getElementById('chatMessages');
      if (container) container.innerHTML = '';
      addMessage("Hi again! I'm here for you. What would you like to talk about? 💜", 'bot');
      await startSession();
    }

    renderRecentConversations();
  } catch (error) {
    console.error('Delete failed:', error);
    showToast('❌ Could not delete conversation');
  }
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = String(text || '');
  return div.innerHTML;
}

// Local knowledge base used when the backend API is unreachable
// (so the companion still answers a wide range of questions offline).
const LOCAL_KNOWLEDGE = [
  {
    match: ['what is ai', 'what is artificial intelligence', 'define ai'],
    reply: "**AI (Artificial Intelligence)** is technology that lets machines learn from data and perform tasks that normally need human intelligence — understanding language, recognizing images, making decisions, and predicting outcomes. It powers tools like chatbots and career-matching platforms. Want me to suggest AI skills to learn based on your profile? 🚀"
  },
  {
    match: ['what is machine learning', 'what is ml', 'define machine learning'],
    reply: "**Machine Learning (ML)** is a branch of AI where computers learn patterns from data without being explicitly programmed. Key types: supervised learning, unsupervised learning, and reinforcement learning. Want to know how to start learning ML for your career? 🤖"
  },
  {
    match: ['how to write a resume', 'resume tips', 'resume format', 'cv writing'],
    reply: "Here's a resume that gets noticed:\n• **Quantify results** — 'grew revenue 40%' beats 'led projects'\n• **Use action verbs** — launched, scaled, negotiated, transformed\n• **Tailor per job** — mirror keywords from the description\n• **Keep it clean** — 1 page under 10 years experience, ATS-friendly\n\nWant me to help strengthen a specific bullet point or section? 💼"
  },
  {
    match: ['how to get a promotion', 'get promoted', 'ask for promotion'],
    reply: "Getting promoted is about visibility + evidence + the ask:\n1. **Know the criteria** — what does the next level actually require?\n2. **Document wins** — track weekly so you don't forget by review time\n3. **Get visible** — present results to leadership, own high-impact projects\n4. **Find a champion** — someone who advocates for you\n5. **Make the ask** — present your case with evidence\n\nWhat role do you want to reach? 💪"
  },
  {
    match: ['how to be more confident', 'build confidence', 'gain confidence', 'confident'],
    reply: "Confidence is built through action, not waiting to 'feel' ready:\n1. **Small wins** — set and achieve one tiny goal daily\n2. **Preparation** — you feel confident when prepared\n3. **Body language** — posture, eye contact, voice ('act as if')\n4. **Mindset** — swap 'I hope' for 'I am'\n\nWhat specific situation do you want to feel confident in? 🌟"
  },
  {
    match: ['how to reduce stress', 'manage stress', 'lower stress', 'anxiety at work'],
    reply: "Here are techniques that actually work for stress:\n• **Breathe** — try 4-7-8: inhale 4s, hold 7s, exhale 8s\n• **Move** — a 10-minute walk shifts stress hormones\n• **Prioritize** — cut your list to 3 things today\n• **Boundaries** — say no to non-essentials\n\nWant to do a quick guided breathing exercise together? 💜"
  },
  {
    match: ['how to sleep better', 'improve sleep', 'can\'t sleep', 'sleep tips'],
    reply: "Better sleep transforms your energy and focus. Try:\n• **Consistent schedule** — same wake time daily\n• **Wind-down ritual** — screens off 45 min before bed\n• **Cool, dark room** — ideal temp ~18-20°C\n• **Limit caffeine** — none after early afternoon\n\nSleep is a performance tool, not a luxury. 🌙"
  },
  {
    match: ['how to network', 'networking tips', 'build professional network'],
    reply: "Networking is about genuine relationships, not collecting contacts:\n• **Give first** — share resources and introductions before asking\n• **Be specific** — 'I'd love to learn about your path to X' beats 'Can we connect?'\n• **Follow up** — personalized note within 24 hours\n• **Nurture** — check in every 60-90 days\n\nThis week: reach out to 1 person you admire. Want help drafting that message? 🤝"
  },
  {
    match: ['how to find a mentor', 'mentor', 'mentorship'],
    reply: "Here's how to find a great mentor:\n• **Look nearby** — senior colleagues, managers, or alumni\n• **Be specific** — ask for advice on a *specific* thing\n• **Offer value** — good mentoring is reciprocal\n• **Start small** — a 30-min coffee chat, not a formal arrangement\n\nWhat area of your career most needs a mentor right now? 🌱"
  },
  {
    match: ['what skills should i learn', 'in demand skills', 'skills for career', 'future skills'],
    reply: "Some of the most in-demand skills right now:\n• **Digital/tech** — AI, data literacy, SQL, Python, cybersecurity\n• **Human** — communication, emotional intelligence, leadership, adaptability\n• **Business** — product thinking, negotiation, project management\n\nA smart mix: 1 technical skill + 1 human skill. What role are you aiming for? 🎯"
  },
  {
    match: ['how to balance work and life', 'work life balance tips', 'manage work and life'],
    reply: "Work-life balance is really about **intentional energy allocation**:\n1. **Set boundaries** — decide when work 'ends' and protect it\n2. **Time-block** — schedule deep work AND rest deliberately\n3. **Learn to say no** — gracefully decline what doesn't serve you\n4. **Recharge rituals** — move, sleep, do something for joy\n\nStart with one boundary this week. Which one feels most important? ⚖️"
  },
  {
    match: ['thank you', 'thanks', 'thank u', 'thx', 'ty'],
    reply: "You're so welcome! 💜 That's exactly why I'm here. Is there anything else on your mind — career, wellness, or just a chat?",
    score: 1
  },
  {
    match: ['bye', 'goodbye', 'see you', 'good night'],
    reply: "Take care! 💜 I'll be right here whenever you need me. Remember — you're capable of amazing things. Come back anytime! 🌸"
  },
  {
    match: ['tell me a joke', 'joke', 'make me laugh', 'funny'],
    reply: "Why did the developer go broke? Because she used up all her cache! 😄 And here's another: Why do programmers prefer dark mode? Because light attracts bugs! 🐛\n\nFeeling lighter? What's on your mind today?"
  },
  {
    match: ['how are you', 'how r u', 'how are you doing', 'what\'s up', 'whats up', 'how is it going'],
    reply: "I'm doing great, thanks for asking! 💜 More importantly, how are YOU doing today — energized, stressed, or somewhere in between?"
  }
];

function getLocalReply(message) {
  const msg = String(message || '').toLowerCase();

  // 1. Greetings
  if (/^(hi+|hello+|hey+|hiya|yo|hii|good (morning|afternoon|evening))(\s|[!?.-])*$/i.test(msg.trim())) {
    const greetingReplies = [
      'Hi! I can help with interview prep, career growth, wellness, or a quick check-in. What do you want to work on?',
      'Hello — glad you’re here. We can jump into a mock interview, career planning, or just talk through what’s on your mind.',
      'Hey! Tell me what you need today and I’ll keep it focused — career, wellness, or both.'
    ];

    const hash = msg.split('').reduce((sum, char) => sum + char.charCodeAt(0), 0);
    return greetingReplies[hash % greetingReplies.length];
  }

  // 2. Matching knowledge base entries
  let bestMatch = null;
  let bestScore = 0;
  for (const item of LOCAL_KNOWLEDGE) {
    let score = 0;
    for (const kw of item.match) {
      if (msg.includes(kw)) {
        score += kw.length > 8 ? 2 : 1;
      }
    }
    if (score > bestScore) {
      bestScore = score;
      bestMatch = item;
    }
  }
  if (bestMatch && bestScore > 0) {
    return bestMatch.reply;
  }

  // 3. Intent-based quick answers
  if (msg.includes('salary') || msg.includes('negotiat')) {
    return 'Great question about salary negotiation! Women who anchor high get better outcomes. Key tip: never accept the first offer, and quantify your value in 3 measurable wins. Want me to draft a script? 💰';
  }
  if (msg.includes('burnout') || msg.includes('stress') || msg.includes('overwhelmed')) {
    return "I hear you. Let's make a plan: 1) Reduce to 3 priorities 2) Take breathing breaks 3) Talk it through. What's causing it most right now? 💜";
  }
  if (msg.includes('interview')) {
    return "Let's prepare! Use the STAR method (Situation, Task, Action, Result) for behavioral questions, and prep a 2-minute 'tell me about yourself' — past → present → future. Want a mock question to practice? 🎯";
  }
  if (msg.includes('cycle') || msg.includes('period') || msg.includes('luteal')) {
    return 'Great awareness! During your **luteal phase**, focus on deep work and wrapping up tasks. Save big presentations and pitches for your **follicular phase** when energy peaks. Want me to plan your week around your cycle? 🩸';
  }
  if (msg.includes('imposter')) {
    return 'Imposter syndrome affects 70-80% of high-achieving women. Keep a wins document, fact-check your thoughts, and talk about it openly. You earned your seat at the table! 💪';
  }

  // 4. Open-question fallback — answer helpfully by topic, never deflect
  const isQuestion = /(\?|what|how|why|when|where|who|can you|tell me|explain|help me)/i.test(msg);
  if (isQuestion) {
    const topic = msg.match(/job|career|role|work|promotion|resume|salary|skills|manager|industry/) ? 'career'
      : msg.match(/stress|anxiety|sleep|mood|energy|balance|boundary|health|feel|tired/) ? 'wellness'
      : msg.match(/ai|machine learning|coding|software|python|data|technology|app|website/) ? 'tech'
      : msg.match(/learn|study|course|education|degree|certification/) ? 'learning'
      : 'general';

    const topicReplies = {
      career: "That's a great career question. The practical approach:\n1. **Clarify your goal** — what outcome do you want in the next 6-12 months?\n2. **Build the evidence** — collect achievements and quantify your impact\n3. **Get visible** — share your work with leadership\n4. **Invest in skills** — close the gap to your target role\n\nWant me to go deeper on any step? 💼",
      wellness: "I hear you — and your well-being matters. A supportive starting point:\n• **Name the feeling** — getting specific reduces its power\n• **Protect your energy** — set one boundary today\n• **Move & breathe** — a short walk or 5 deep breaths resets your nervous system\n• **Reach out** — you don't have to carry it alone\n\nHow are you feeling right now, honestly? I'm here with you. 💜",
      tech: "Great technical question! A solid approach:\n1. **Start with the fundamentals** — core concept before tools\n2. **Practice by building** — small projects teach more than tutorials\n3. **Understand the 'why'** — not just the syntax\n4. **Keep it current** — follow good sources\n\nWhat specific technology are you exploring? 💻",
      learning: "Learning is a superpower — here's how to make it stick:\n• **Set a clear goal** — learn something specific, not 'everything'\n• **Use active recall** — practice and test yourself\n• **Spaced repetition** — review at intervals\n• **Apply it** — use what you learn in a real project\n\nWhat subject are you interested in? 📚",
      general: "That's a thoughtful question. My take:\n• **Break it down** — separate the key parts\n• **Consider the goal** — what would a good outcome look like?\n• **Take one step** — act on the most important part first\n• **Stay curious** — keep refining as you learn\n\nIs this about your career, wellness, or something else? I'm here to help. 💜"
    };
    return topicReplies[topic];
  }

  // 5. Final fallback
  const generalReplies = [
    'I can help with career growth, interview prep, or wellness support. What would you like to focus on?',
    'Tell me a bit more and I’ll tailor the advice to your situation — career, wellness, or both.',
    'I’m here with you. If you share the goal, I’ll keep the next step simple and specific.'
  ];

  const hash = msg.split('').reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return generalReplies[hash % generalReplies.length];
}

async function sendToAI(message) {
  try {
    if (!currentSessionId || String(currentSessionId).startsWith('local_session_')) {
      await startSession();
    }

    const data = await api.post('/chat/message', {
      sessionId: currentSessionId,
      message
    });
    return data.response || "I'm here for you. Could you tell me more? 💜";
  } catch (error) {
    console.error('AI response failed:', error);

    if (error.status === 404 || error.status === 401) {
      currentSessionId = null;
      try {
        await startSession();
        const retry = await api.post('/chat/message', {
          sessionId: currentSessionId,
          message
        });
        return retry.response || getLocalReply(message);
      } catch (retryError) {
        console.error('Retry failed:', retryError);
      }
    }

    return getLocalReply(message);
  }
}

// ============ CHAT UI FUNCTIONS ============
async function sendMessage() {
  const input = document.getElementById('chatInput');
  if (!input) return;
  const message = input.value.trim();
  if (!message) return;

  // Add user message
  addMessage(message, 'user');
  input.value = '';
  input.focus();

  // Show typing indicator
  showTyping();

  try {
    // Get AI response from backend (with fallback)
    const response = await sendToAI(message);
    hideTyping();
    addMessage(response, 'bot');
    saveConversation();
  } catch (error) {
    hideTyping();
    addMessage("I'm having trouble connecting right now. Please try again in a moment. 💜", 'bot');
  }
}

let isTTSEnabled = false;
let recognition = null;
let isRecording = false;

function toggleTTS() {
  isTTSEnabled = !isTTSEnabled;
  const icon = document.getElementById('ttsIcon');
  const btn = document.getElementById('ttsToggleBtn');
  if (icon) {
    icon.className = isTTSEnabled ? 'fas fa-volume-up' : 'fas fa-volume-mute';
    if (btn) btn.style.color = isTTSEnabled ? 'var(--rose)' : 'var(--text-muted)';
  }
  if (!isTTSEnabled && window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
  showToast(isTTSEnabled ? '🔊 Voice response enabled' : '🔇 Voice response muted');
}

function speakText(text) {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel(); // stop previous speech

  const cleanText = text.replace(/<[^>]*>/g, '').replace(/[*_#•]/g, ' ');
  const utterance = new SpeechSynthesisUtterance(cleanText);
  utterance.rate = 0.95;
  utterance.pitch = 1.05;

  const voices = window.speechSynthesis.getVoices();
  const femaleVoice = voices.find(v => v.lang.startsWith('en') && (v.name.includes('Female') || v.name.includes('Google') || v.name.includes('Natural') || v.name.includes('Samantha') || v.name.includes('Zira')));
  if (femaleVoice) {
    utterance.voice = femaleVoice;
  }

  window.speechSynthesis.speak(utterance);
}

function toggleVoiceInput() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showToast('⚠️ Speech recognition not supported in this browser. Try Chrome or Edge.');
    return;
  }

  const micBtn = document.getElementById('voiceBtn');
  const micIcon = document.getElementById('micIcon');
  const chatInput = document.getElementById('chatInput');

  if (isRecording && recognition) {
    recognition.stop();
    isRecording = false;
    if (micBtn) micBtn.classList.remove('recording-pulse');
    if (micIcon) micIcon.className = 'fas fa-microphone';
    if (chatInput) chatInput.placeholder = 'Ask me anything about career or wellness...';
    showToast('🎙️ Voice input stopped');
    return;
  }

  try {
    recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      isRecording = true;
      if (micBtn) micBtn.classList.add('recording-pulse');
      if (micIcon) micIcon.className = 'fas fa-stop';
      if (chatInput) chatInput.placeholder = '🎙️ Listening... Speak now!';
      showToast('🎙️ Listening... Speak your prompt');
    };

    recognition.onresult = (event) => {
      let transcript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      if (chatInput) chatInput.value = transcript;
    };

    recognition.onerror = (event) => {
      console.warn('Speech recognition error:', event.error);
      isRecording = false;
      if (micBtn) micBtn.classList.remove('recording-pulse');
      if (micIcon) micIcon.className = 'fas fa-microphone';
      if (chatInput) chatInput.placeholder = 'Ask me anything about career or wellness...';
      showToast('⚠️ Could not capture audio. Check mic permissions.');
    };

    recognition.onend = () => {
      isRecording = false;
      if (micBtn) micBtn.classList.remove('recording-pulse');
      if (micIcon) micIcon.className = 'fas fa-microphone';
      if (chatInput) chatInput.placeholder = 'Ask me anything about career or wellness...';
    };

    recognition.start();
  } catch (err) {
    console.error('Recognition error:', err);
  }
}

function addMessage(text, sender) {
  const messagesContainer = document.getElementById('chatMessages');
  if (!messagesContainer) return;
  const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  const wrapper = document.createElement('div');
  wrapper.className = `message-wrapper ${sender}`;

  const msgId = 'msg_' + Math.random().toString(36).substring(2, 9);

  if (sender === 'bot') {
    wrapper.innerHTML = `
      <div class="message-avatar">
        <i class="fas fa-robot"></i>
      </div>
      <div class="message-bubble">
        <p>${formatMessage(text)}</p>
        <button class="msg-speak-btn" title="Read Aloud" onclick="speakText(\`${text.replace(/`/g, '\\`').replace(/'/g, "\\'")}\`)">
          <i class="fas fa-volume-up"></i>
        </button>
      </div>
      <span class="message-time">${time}</span>
    `;
    if (isTTSEnabled) {
      speakText(text);
    }
  } else {
    wrapper.innerHTML = `
      <span class="message-time">${time}</span>
      <div class="message-bubble">
        <p>${formatMessage(text)}</p>
      </div>
      <div class="message-avatar user-avatar">P</div>
    `;
  }

  messagesContainer.appendChild(wrapper);
  scrollToBottom();

  // Save to state
  conversationState.messages.push({ text, sender, time });
}

function formatMessage(text) {
  // Convert markdown-like syntax safely
  const escaped = String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
  return escaped
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
    .replace(/•/g, '<br>•');
}

function showTyping() {
  const el = document.getElementById('typingIndicator');
  if (el) el.style.display = 'block';
  scrollToBottom();
}

function hideTyping() {
  const el = document.getElementById('typingIndicator');
  if (el) el.style.display = 'none';
}

function scrollToBottom() {
  const messagesContainer = document.getElementById('chatMessages');
  if (!messagesContainer) return;
  setTimeout(() => {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }, 100);
}

function handleChatKey(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
}

function quickPrompt(promptText) {
  const input = document.getElementById('chatInput');
  if (!input) return;
  input.value = promptText;
  sendMessage();
}

function clearChat() {
  if (confirm('Clear this conversation? This cannot be undone.')) {
    const container = document.getElementById('chatMessages');
    if (container) container.innerHTML = '';
    conversationState.messages = [];
    localStorage.removeItem('aviraaChatHistory');
    showToast('Conversation cleared 🗑️');

    // Add back welcome message
    setTimeout(() => {
      addMessage("Hi again! I'm here for you. What would you like to talk about? 💜", 'bot');
    }, 300);
  }
}

function exportChat() {
  let exportText = 'Aviraa AI Companion - Chat History\n';
  exportText += '='.repeat(40) + '\n\n';

  conversationState.messages.forEach(msg => {
    const sender = msg.sender === 'user' ? 'You' : 'Aviraa';
    exportText += `[${msg.time}] ${sender}:\n${msg.text}\n\n`;
  });

  const blob = new Blob([exportText], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `aviraa-chat-${new Date().toISOString().split('T')[0]}.txt`;
  a.click();
  URL.revokeObjectURL(url);
  showToast('📥 Chat exported!');
}

function saveConversation() {
  // Keep only last 50 messages
  if (conversationState.messages.length > 50) {
    conversationState.messages = conversationState.messages.slice(-50);
  }
  localStorage.setItem('aviraaChatHistory', JSON.stringify(conversationState.messages));
}

// ============ TOAST ============
function showToast(message) {
  const existingToast = document.querySelector('.toast');
  if (existingToast) existingToast.remove();

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

loadHistory();

  // Focus input
  const input = document.getElementById('chatInput');
  if (input) input.focus();

  // Add toast styles
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

  console.log('🤖 Aviraa AI Companion ready!');
});

// Expose functions globally
window.sendMessage = sendMessage;
window.handleChatKey = handleChatKey;
window.quickPrompt = quickPrompt;
window.clearChat = clearChat;
window.exportChat = exportChat;
window.showToast = showToast;
window.resumeConversation = resumeConversation;
window.deleteConversation = deleteConversation;
window.toggleVoiceInput = toggleVoiceInput;
window.toggleTTS = toggleTTS;
window.speakText = speakText;
