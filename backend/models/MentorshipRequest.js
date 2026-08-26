const mongoose = require('mongoose');

const mentorshipRequestSchema = new mongoose.Schema(
  {
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'User',
      required: true
    },
    mentor: {
      type: mongoose.Schema.Types.ObjectId,
      ref: 'Mentor',
      required: true
    },
    topic: {
      type: String,
      default: 'Career Growth',
      trim: true
    },
    preferredTime: {
      type: String,
      default: 'Flexible',
      trim: true
    },
    note: {
      type: String,
      default: '',
      trim: true,
      maxlength: 1000
    },
    status: {
      type: String,
      enum: ['pending', 'accepted', 'rejected', 'completed', 'cancelled'],
      default: 'pending'
    }
  },
  { timestamps: true }
);

// Prevent duplicate pending requests for same user + mentor
mentorshipRequestSchema.index(
  { user: 1, mentor: 1, status: 1 },
  { unique: true, partialFilterExpression: { status: 'pending' } }
);

module.exports = mongoose.model('MentorshipRequest', mentorshipRequestSchema);