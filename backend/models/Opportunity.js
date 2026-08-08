const mongoose = require('mongoose');

const opportunitySchema = new mongoose.Schema({
  title: {
    type: String,
    required: true
  },
  type: {
    type: String,
    enum: ['job', 'course', 'mentorship', 'freelance'],
    required: true
  },
  company: String,
  provider: String,
  location: String,
  salary: String,
  duration: String,
  description: String,
  requirements: [String],
  tags: [String],
  matchScore: Number,
  postedDate: {
    type: Date,
    default: Date.now
  },
  expiresAt: Date,
  isActive: {
    type: Boolean,
    default: true
  },
  applicants: [{
    user: { type: mongoose.Schema.Types.ObjectId, ref: 'User' },
    appliedDate: { type: Date, default: Date.now },
    status: { type: String, enum: ['pending', 'reviewed', 'shortlisted', 'rejected'], default: 'pending' }
  }]
});

module.exports = mongoose.model('Opportunity', opportunitySchema);