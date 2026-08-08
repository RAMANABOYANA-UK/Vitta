const mongoose = require('mongoose');

const mentorSchema = new mongoose.Schema({
  name: {
    type: String,
    required: true,
    trim: true
  },
  title: {
    type: String,
    required: true
  },
  company: {
    type: String,
    required: true
  },
  avatar: {
    type: String,
    default: ''
  },
  category: {
    type: String,
    enum: ['Career', 'Tech', 'Leadership', 'Wellness', 'Entrepreneurship'],
    default: 'Career'
  },
  expertise: [{
    type: String,
    trim: true
  }],
  bio: {
    type: String,
    required: true
  },
  rating: {
    type: Number,
    default: 4.9
  },
  sessionCount: {
    type: Number,
    default: 45
  },
  availability: {
    type: String,
    default: 'Available this week'
  },
  hourlyRate: {
    type: String,
    default: 'Free (Community)'
  },
  matchScore: {
    type: Number,
    default: 92
  },
  createdAt: {
    type: Date,
    default: Date.now
  }
});

module.exports = mongoose.model('Mentor', mentorSchema);
