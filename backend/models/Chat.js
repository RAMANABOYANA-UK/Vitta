const mongoose = require('mongoose');

const chatSchema = new mongoose.Schema({
  user: {
    type: mongoose.Schema.Types.ObjectId,
    ref: 'User',
    required: true
  },
  messages: [{
    role: {
      type: String,
      enum: ['user', 'assistant'],
      required: true
    },
    content: String,
    category: String,
    timestamp: { type: Date, default: Date.now }
  }],
  sessionStart: {
    type: Date,
    default: Date.now
  },
  sessionEnd: Date,
  isActive: {
    type: Boolean,
    default: true
  }
});

module.exports = mongoose.model('Chat', chatSchema);