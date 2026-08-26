const jwt = require('jsonwebtoken');
const User = require('../models/User');
const Career = require('../models/Career');
const Wellness = require('../models/Wellness');
const emailSender = require('../utils/emailSender');

// Generate JWT token
const generateToken = (id) => {
  return jwt.sign({ id }, process.env.JWT_SECRET, {
    expiresIn: process.env.JWT_EXPIRE
  });
};

// @desc    Register user
// @route   POST /api/auth/signup
const signup = async (req, res, next) => {
  try {
    const { name, email, password } = req.body;

    // Check if user exists
    const existingUser = await User.findOne({ email });
    if (existingUser) {
      return res.status(400).json({ message: 'User already exists' });
    }

    const defaultSkills = [
      { name: 'Product Strategy', level: 85, category: 'Product' },
      { name: 'Leadership', level: 70, category: 'Management' },
      { name: 'Data Analysis', level: 60, category: 'Tech' },
      { name: 'Influential Communication', level: 75, category: 'General' }
    ];

    // Create user with rich starter profile
    const user = await User.create({
      name,
      email,
      password,
      currentRole: 'Product Specialist / Engineer',
      targetRole: 'Senior Product Manager / Leader',
      experience: 4,
      skills: defaultSkills
    });

    // Create career and wellness profiles with starter data
    await Career.create({
      user: user._id,
      skills: defaultSkills
    });
    await Wellness.create({
      user: user._id,
      streakDays: 1,
      mood: 'Energized'
    });

    // Generate token
    const token = generateToken(user._id);

    // Send welcome email (uses SMTP if configured, otherwise logs)
    try {
      await emailSender.sendWelcomeEmail(user);
    } catch (welcomeErr) {
      console.warn('Welcome email could not be delivered:', welcomeErr.message);
    }

    res.status(201).json({
      token,
      user: {
        id: user._id,
        name: user.name,
        email: user.email,
        currentRole: user.currentRole,
        targetRole: user.targetRole,
        skills: user.skills
      }
    });
  } catch (error) {
    next(error);
  }
};

// @desc    Login user
// @route   POST /api/auth/login
const login = async (req, res, next) => {
  try {
    const { email, password } = req.body;

    // Find user with password
    const user = await User.findOne({ email }).select('+password');
    if (!user) {
      return res.status(401).json({ message: 'Invalid credentials' });
    }

    // Check password
    const isMatch = await user.comparePassword(password);
    if (!isMatch) {
      return res.status(401).json({ message: 'Invalid credentials' });
    }

    // Generate token
    const token = generateToken(user._id);

    res.json({
      token,
      user: {
        id: user._id,
        name: user.name,
        email: user.email,
        currentRole: user.currentRole,
        targetRole: user.targetRole
      }
    });
  } catch (error) {
    next(error);
  }
};

// @desc    Get user profile
// @route   GET /api/auth/profile
const getProfile = async (req, res, next) => {
  try {
    const user = await User.findById(req.user._id);
    res.json(user);
  } catch (error) {
    next(error);
  }
};

// @desc    Update user profile
// @route   PUT /api/auth/profile
const updateProfile = async (req, res, next) => {
  try {
    const existingUser = await User.findById(req.user._id);
    const updates = { ...req.body };

    if (updates.preferences || existingUser?.preferences) {
      updates.preferences = {
        ...(existingUser?.preferences?.toObject ? existingUser.preferences.toObject() : existingUser?.preferences || {}),
        ...(updates.preferences || {})
      };
    }

const user = await User.findByIdAndUpdate(req.user._id, updates, {
      new: true,
      runValidators: true
    });

    // ─── Sync profile skills into the user's Career document ──────────────
    // When the user edits their profile skills, mirror them into the Career
    // document so Career AI (skills list, skill gaps, learning path) reflects
    // the exact data the user entered. We only overwrite Career skills when the
    // profile explicitly provides a non-empty skills array (i.e. the user edited
    // skills in the profile form).
    if (Array.isArray(updates.skills) && updates.skills.length > 0) {
      try {
        let career = await Career.findOne({ user: req.user._id });
        if (!career) {
          career = await Career.create({ user: req.user._id });
        }
        career.skills = updates.skills.map((s) => ({
          name: String(s.name || '').trim(),
          level: Math.min(100, Math.max(0, Number(s.level) || 50)),
          category: s.category || 'General'
        })).filter((s) => s.name);
        await career.save();
      } catch (syncErr) {
        console.warn('Failed to sync profile skills into Career:', syncErr.message);
      }
    }

    res.json(user);
  } catch (error) {
    next(error);
  }
};

// @desc    Send test digest email to logged in user
// @route   POST /api/auth/send-digest
const sendDigestEmail = async (req, res, next) => {
  try {
    const user = await User.findById(req.user._id);
    if (!user) return res.status(404).json({ message: 'User not found' });

    const wellness = await Wellness.findOne({ user: req.user._id });
    const career = await Career.findOne({ user: req.user._id });

    const result = await emailSender.sendProgressDigest(user, career || {}, wellness || {});
    res.json({
      success: true,
      message: `Digest email processed for ${user.email}`,
      result
    });
  } catch (error) {
    next(error);
  }
};

module.exports = { signup, login, getProfile, updateProfile, sendDigestEmail };