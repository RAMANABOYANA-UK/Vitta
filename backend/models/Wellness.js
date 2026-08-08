const mongoose = require('mongoose');

const wellnessSchema = new mongoose.Schema({
  user: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  moods: [{
    mood: String,
    emoji: String,
    note: String,
    date: { type: Date, default: Date.now }
  }],
  sleep: [{
    hours: Number,
    quality: { type: Number, min: 1, max: 5 },
    date: { type: Date, default: Date.now }
  }],
  water: [{
    glasses: Number,
    date: { type: Date, default: Date.now }
  }],
  exercise: [{
    type: { type: String },
    duration: Number,
    date: { type: Date, default: Date.now }
  }],
  cycleLog: [{
    phase: String,
    symptoms: [String],
    energyLevel: Number,
    date: { type: Date, default: Date.now }
  }],
  stressLevels: [{
    level: { type: Number, min: 1, max: 10 },
    triggers: [String],
    date: { type: Date, default: Date.now }
  }],
  streak: {
    type: Number,
    default: 0
  },
  lastCheckIn: Date,
  createdAt: {
    type: Date,
    default: Date.now
  }
});

module.exports = mongoose.model('Wellness', wellnessSchema);