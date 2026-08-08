const Opportunity = require('../models/Opportunity');
const SavedOpportunity = require('../models/SavedOpportunity');
const User = require('../models/User');
const { predictMatchScore } = require('../utils/aiHelper');

const getOpportunities = async (req, res, next) => {
  try {
    const { type, search, sort } = req.query;
    let query = { isActive: true };

    if (type && type !== 'all') {
      query.type = type;
    }

    if (search) {
      query.$or = [
        { title: { $regex: search, $options: 'i' } },
        { company: { $regex: search, $options: 'i' } },
        { description: { $regex: search, $options: 'i' } },
        { tags: { $regex: search, $options: 'i' } }
      ];
    }

    let sortOption = { matchScore: -1 };
    if (sort === 'recent') sortOption = { postedDate: -1 };

    const opportunities = await Opportunity.find(query);
    
    // Get user for ML-based personalization
    const user = await User.findById(req.user._id);

    // Compute personalized match scores using ML helper
    const personalized = opportunities.map(opp => {
      const mlScore = predictMatchScore(user || {}, opp);
      return {
        ...opp.toObject(),
        matchScore: opp.matchScore || mlScore,
        mlMatchScore: mlScore,
        isPersonalized: true
      };
    });

    // Sort by ML score if no explicit sort
    if (!sort) {
      personalized.sort((a, b) => (b.mlMatchScore || b.matchScore) - (a.mlMatchScore || a.matchScore));
    }

    res.json(personalized);
  } catch (error) {
    next(error);
  }
};

const saveOpportunity = async (req, res, next) => {
  try {
    const existing = await SavedOpportunity.findOne({
      user: req.user._id,
      opportunity: req.params.id
    });

    if (existing) {
      return res.status(200).json({ message: 'Already saved', saved: true });
    }

    const saved = await SavedOpportunity.create({
      user: req.user._id,
      opportunity: req.params.id
    });
    res.status(201).json(saved);
  } catch (error) {
    next(error);
  }
};

const applyOpportunity = async (req, res, next) => {
  try {
    const opportunity = await Opportunity.findById(req.params.id);
    if (!opportunity) {
      return res.status(404).json({ message: 'Opportunity not found' });
    }

    // Check if already applied
    const alreadyApplied = opportunity.applicants.some(a => a.user.toString() === req.user._id.toString());
    if (alreadyApplied) {
      return res.status(200).json({ message: 'Already applied', applied: true });
    }

    opportunity.applicants.push({
      user: req.user._id,
      appliedDate: new Date(),
      status: 'pending'
    });

    await opportunity.save();
    res.status(201).json({ message: 'Application submitted successfully', applied: true });
  } catch (error) {
    next(error);
  }
};

module.exports = { getOpportunities, saveOpportunity, applyOpportunity };