const mongoose = require('mongoose');
const Chat = require('../models/Chat');
const User = require('../models/User');
const Career = require('../models/Career');
const Wellness = require('../models/Wellness');
const { generateAIResponse, determineCyclePhase, classifyIntent } = require('../utils/aiHelper');
const { generateLLMResponse } = require('../utils/llmHelper');
const { isHarmfulContent, getSafeFallbackResponse } = require('../utils/contentSafety');

const startSession = async (req, res, next) => {
  try {
    const chat = await Chat.create({
      user: req.user._id,
      messages: [],
      sessionStart: new Date()
    });
    res.status(201).json({ sessionId: chat._id });
  } catch (error) {
    next(error);
  }
};

/**
 * Resume the most recent active session for the user.
 * If none exists, create a new one. Returns the session + its history.
 */
const resumeSession = async (req, res, next) => {
  try {
    let chat = await Chat.findOne({
      user: req.user._id,
      isActive: true
    })
      .sort({ sessionStart: -1 })
      .limit(1);

    if (!chat) {
      chat = await Chat.create({
        user: req.user._id,
        messages: [],
        sessionStart: new Date()
      });
    }

    res.json({
      sessionId: chat._id,
      messages: chat.messages || [],
      sessionStart: chat.sessionStart
    });
  } catch (error) {
    next(error);
  }
};

/**
 * Mark a session as ended (soft delete) so it no longer resumes by default,
 * but the data is preserved.
 */
const endSession = async (req, res, next) => {
  try {
    const { id } = req.params;

    if (!mongoose.Types.ObjectId.isValid(id)) {
      return res.status(404).json({ message: 'Session not found' });
    }

    const chat = await Chat.findOne({
      _id: id,
      user: req.user._id
    });

    if (!chat) {
      return res.status(404).json({ message: 'Session not found' });
    }

    chat.isActive = false;
    chat.sessionEnd = new Date();
    await chat.save();

    res.json({ message: 'Session ended', sessionId: chat._id });
  } catch (error) {
    next(error);
  }
};

/**
 * Permanently delete a session.
 */
const deleteSession = async (req, res, next) => {
  try {
    const { id } = req.params;

    if (!mongoose.Types.ObjectId.isValid(id)) {
      return res.status(404).json({ message: 'Session not found' });
    }

    const result = await Chat.findOneAndDelete({
      _id: id,
      user: req.user._id
    });

    if (!result) {
      return res.status(404).json({ message: 'Session not found' });
    }

    res.json({ message: 'Session deleted', sessionId: result._id });
  } catch (error) {
    next(error);
  }
};

const sendMessage = async (req, res, next) => {
  try {
    const { sessionId, message } = req.body;

    if (!sessionId || !message || !message.trim()) {
      return res.status(400).json({ message: 'Session ID and message are required' });
    }

    if (!mongoose.Types.ObjectId.isValid(sessionId)) {
      return res.status(404).json({ message: 'Session not found' });
    }

    const chat = await Chat.findOne({
      _id: sessionId,
      user: req.user._id,
      isActive: true
    });

    if (!chat) {
      return res.status(404).json({ message: 'Session not found' });
    }

    // ─── Safety: Block harmful/abusive/vulgar content ──────────────────
    if (isHarmfulContent(message)) {
      // Still log the user message (for record) but respond safely
      chat.messages.push({
        role: 'user',
        content: message
      });

      const safeResponse = getSafeFallbackResponse();

      chat.messages.push({
        role: 'assistant',
        content: safeResponse,
        category: 'moderated'
      });

      await chat.save();

      return res.json({
        response: safeResponse,
        engine: 'safety',
        moderated: true
      });
    }

    // Add user message
    chat.messages.push({
      role: 'user',
      content: message
    });

    // Load user context for personalization
    const [user, career, wellness] = await Promise.all([
      User.findById(req.user._id),
      Career.findOne({ user: req.user._id }),
      Wellness.findOne({ user: req.user._id })
    ]);

    let response = null;
    let isLLM = false;

    // Try real LLM API first (if OPENAI_API_KEY is configured)
    const cyclePhase = determineCyclePhase(user?.cycleData);
    const chatHistory = chat.messages
      .filter(m => m.role !== 'system' && m.category !== 'moderated')
      .slice(-6)
      .map(m => ({ role: m.role, content: m.content }));

    const llmResponse = await generateLLMResponse(message, {
      user: user || {},
      career: career || {},
      wellness: wellness || {},
      cyclePhase,
      chatHistory
    });

    let intent = 'general';
    let category = 'general';
    let followUp = null;
    let confidence = 0;

    if (llmResponse) {
      response = llmResponse;
      isLLM = true;
      // Classify intent for metadata even on LLM responses
      const cls = classifyIntent(message);
      intent = cls.intent;
      category = cls.category;
      confidence = cls.confidence;
    } else {
      // Fallback to local engine (knowledge base + intent templates + open-question fallback)
      const mlResult = generateAIResponse(message, { user, career, wellness });
      response = mlResult.response;
      intent = mlResult.intent;
      category = mlResult.category;
      followUp = mlResult.followUp;
      confidence = mlResult.confidence;
    }

    // Add AI response
    chat.messages.push({
      role: 'assistant',
      content: response,
      category: isLLM ? 'llm' : null
    });

    await chat.save();

    res.json({
      response,
      engine: isLLM ? 'llm' : 'ml',
      sessionId: chat._id,
      intent,
      category,
      followUp,
      confidence
    });
  } catch (error) {
    next(error);
  }
};

const getHistory = async (req, res, next) => {
  try {
    const chats = await Chat.find({ user: req.user._id })
      .sort({ sessionStart: -1 })
      .limit(10);
    res.json(chats);
  } catch (error) {
    next(error);
  }
};

module.exports = { startSession, resumeSession, endSession, deleteSession, sendMessage, getHistory };
