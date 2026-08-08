const mongoose = require('mongoose');

const careerSchema = new mongoose.Schema({
  user: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  skills: [{
    name: String,
    level: { type: Number, min: 0, max: 100 },
    category: String
  }],
  goals: [{
    title: String,
    targetDate: Date,
    status: { type: String, enum: ['active', 'completed', 'paused'], default: 'active' },
    progress: { type: Number, default: 0 }
  }],
  resumeUrl: String,
  linkedinUrl: String,
  careerPath: [{
    role: String,
    company: String,
    startDate: Date,
    endDate: Date,
    isCurrent: Boolean
  }],
  aiInsights: [{
    message: String,
    category: String,
    date: { type: Date, default: Date.now }
  }],
  createdAt: {
    type: Date,
    default: Date.now
  },
  updatedAt: {
    type: Date,
    default: Date.now
  }
});

careerSchema.pre('save', function(next) {
  this.updatedAt = Date.now();
  next();
});

module.exports = mongoose.model('Career', careerSchema);