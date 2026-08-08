const Career = require('../models/Career');
const Wellness = require('../models/Wellness');
const Chat = require('../models/Chat');
const Opportunity = require('../models/Opportunity');
const User = require('../models/User');
const { generateDailyInsight, determineCyclePhase } = require('../utils/aiHelper');

// @desc    Get dashboard summary
// @route   GET /api/dashboard
const getDashboard = async (req, res, next) => {
  try {
    const userId = req.user._id;

    // Get all data in parallel
    const [user, career, wellness, opportunityCount, recentChats] = await Promise.all([
      User.findById(userId),
      Career.findOne({ user: userId }),
      Wellness.findOne({ user: userId }),
      Opportunity.countDocuments({ isActive: true }),
      Chat.find({ user: userId, isActive: true })
        .sort({ sessionStart: -1 })
        .limit(5)
    ]);

    const careerProgress = career 
      ? Math.round(career.skills.reduce((acc, s) => acc + s.level, 0) / (career.skills.length || 1))
      : 0;
    const wellnessStreak = wellness ? wellness.streak : 0;

    // Get recent activity
    const recentMoods = wellness ? wellness.moods.slice(-3) : [];
    const recentCareerGoals = career ? career.goals.filter(g => g.status === 'active').slice(0, 3) : [];

    // Generate ML-powered daily insight
    const insight = generateDailyInsight({ user, career, wellness });

    // Cycle phase for display
    const cyclePhase = determineCyclePhase(user?.cycleData);

    res.json({
      careerProgress,
      wellnessStreak,
      opportunityCount,
      recentChats: recentChats.length,
      recentMoods,
      recentCareerGoals,
      aiInsight: insight.insight,
      aiInsightCategory: insight.category,
      aiInsightReason: insight.reason,
      cyclePhase,
      career: career || { skills: [], goals: [] },
      wellness: wellness || { streak: 0, moods: [], sleep: [], water: [] }
    });
  } catch (error) {
    next(error);
  }
};

module.exports = { getDashboard };