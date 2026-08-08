/**
 * Aviraa LLM Helper - Real LLM API integration
 *
 * Primary: Google Gemini (GEMINI_API_KEY)
 * Secondary: OpenAI-compatible APIs (OPENAI_API_KEY / OPENAI_API_URL / OPENAI_MODEL)
 * Falls back gracefully to the local ML engine when no API key is configured.
 *
 * Environment variables:
 *   GEMINI_API_KEY  - Google Gemini API key (required for Gemini mode)
 *   GEMINI_MODEL    - Gemini model (default: gemini-1.5-flash)
 *   GEMINI_API_URL  - Gemini API base URL (default: https://generativelanguage.googleapis.com/v1beta)
 *   OPENAI_API_KEY  - OpenAI-compatible API key (fallback mode)
 *   OPENAI_API_URL  - OpenAI-compatible base URL (default: https://api.openai.com/v1)
 *   OPENAI_MODEL    - OpenAI-compatible model (default: gpt-4o-mini)
 */
const { buildSafeSystemPrompt } = require('./contentSafety');

// ─── System Prompt ──────────────────────────────────────────────────────────

function buildSystemPrompt(context = {}) {
  return buildSafeSystemPrompt(context);
}

// ─── Gemini ─────────────────────────────────────────────────────────────────

/**
 * Call the Google Gemini generateContent API.
 * @param {string} message - User message
 * @param {object} context - { user, career, wellness, chatHistory }
 * @returns {Promise<string|null>} - Response text or null on failure
 */
async function generateGeminiResponse(message, context = {}) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    console.log('No GEMINI_API_KEY configured - checking other LLM options');
    return null;
  }

  const model = process.env.GEMINI_MODEL || 'gemini-1.5-flash';
  const baseUrl = (process.env.GEMINI_API_URL || 'https://generativelanguage.googleapis.com/v1beta').replace(/\/$/, '');

  const contents = buildGeminiContents(message, context);

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);

    const response = await fetch(
      `${baseUrl}/models/${model}:generateContent?key=${encodeURIComponent(apiKey)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contents,
          systemInstruction: { parts: [{ text: buildSystemPrompt(context) }] },
          generationConfig: {
            temperature: 0.7,
            maxOutputTokens: 900,
            topP: 0.9,
            topK: 40
          }
        }),
        signal: controller.signal
      }
    );

    clearTimeout(timeout);

    if (!response.ok) {
      const errText = await response.text().catch(() => '');
      console.warn(`Gemini API error ${response.status}: ${errText.slice(0, 300)}`);
      return null;
    }

    const data = await response.json();
    const parts = data?.candidates?.[0]?.content?.parts;
    const text = Array.isArray(parts) ? parts.map(p => p.text || '').join('').trim() : '';
    return text || null;
  } catch (error) {
    clearTimeout(timeout);
    console.warn(`Gemini API request failed: ${error.message}`);
    return null;
  }
}

/**
 * Build the Gemini `contents` array from chat history + current message,
 * ensuring alternating user/model roles (Gemini requirement).
 */
function buildGeminiContents(message, context = {}) {
  const contents = [];
  let lastRole = null;

  const history = (context.chatHistory || []).slice(-8);
  for (const m of history) {
    const role = m.role === 'assistant' ? 'model' : 'user';
    if (lastRole === role) continue; // keep roles alternating
    contents.push({ role, parts: [{ text: m.content }] });
    lastRole = role;
  }

  if (lastRole === 'user') {
    // Merge with the current message to avoid two consecutive user turns
    const last = contents[contents.length - 1];
    last.parts[0].text = `${last.parts[0].text}\n\n${message}`;
  } else {
    contents.push({ role: 'user', parts: [{ text: message }] });
  }

  // Gemini requires the first content role to be 'user'
  while (contents.length && contents[0].role !== 'user') {
    contents.shift();
  }
  if (contents.length === 0) {
    contents.push({ role: 'user', parts: [{ text: message }] });
  }

  return contents;
}

// ─── OpenAI-compatible (fallback) ───────────────────────────────────────────

async function generateOpenAIResponse(message, context = {}) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) return null;

  const apiUrl = (process.env.OPENAI_API_URL || 'https://api.openai.com/v1').replace(/\/$/, '');
  const model = process.env.OPENAI_MODEL || 'gpt-4o-mini';

  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30000);

    const response = await fetch(`${apiUrl}/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model,
        messages: [
          { role: 'system', content: buildSystemPrompt(context) },
          ...(context.chatHistory || []).slice(-6),
          { role: 'user', content: message }
        ],
        temperature: 0.7,
        max_tokens: 600,
        top_p: 0.9
      }),
      signal: controller.signal
    });

    clearTimeout(timeout);

    if (!response.ok) {
      const errText = await response.text().catch(() => '');
      console.warn(`LLM API error ${response.status}: ${errText.slice(0, 200)}`);
      return null;
    }

    const data = await response.json();
    return data.choices?.[0]?.message?.content || null;
  } catch (error) {
    clearTimeout(timeout);
    console.warn(`LLM API request failed: ${error.message}`);
    return null;
  }
}

// ─── Public API ─────────────────────────────────────────────────────────────

/**
 * Generate an LLM response using Gemini (primary) or OpenAI-compatible (fallback).
 * Returns null when no API key is configured, so the caller can use the local engine.
 */
async function generateLLMResponse(message, context = {}) {
  // Try Gemini first
  const geminiResponse = await generateGeminiResponse(message, context);
  if (geminiResponse) return geminiResponse;

  // Then OpenAI-compatible APIs
  const openAIResponse = await generateOpenAIResponse(message, context);
  if (openAIResponse) return openAIResponse;

  console.log('No LLM API key configured - using local ML engine');
  return null;
}

module.exports = { generateLLMResponse };

