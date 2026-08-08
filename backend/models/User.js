const mongoose = require('mongoose');
const bcrypt = require('bcryptjs');

const userSchema = new mongoose.Schema({
  name: {
    type: String,
    required: [true, 'Name is required'],
    trim: true
  },
  email: {
    type: String,
    required: [true, 'Email is required'],
    unique: true,
    lowercase: true,
    match: [/^\S+@\S+\.\S+$/, 'Please enter a valid email']
  },
  password: {
    type: String,
    required: [true, 'Password is required'],
    minlength: [8, 'Password must be at least 8 characters'],
    select: false
  },
  age: {
    type: Number,
    min: 18
  },
  currentRole: {
    type: String,
    default: ''
  },
  targetRole: {
    type: String,
    default: ''
  },
  experience: {
    type: Number,
    default: 0
  },
  skills: [{
    name: {
      type: String,
      trim: true
    },
    level: {
      type: Number,
      min: 0,
      max: 100,
      default: 50
    },
    category: {
      type: String,
      default: 'General'
    }
  }],
  cycleData: {
    lastPeriodDate: Date,
    cycleLength: { type: Number, default: 28 },
    periodLength: { type: Number, default: 5 }
  },
  preferences: {
    jobTypes: [String],
    locations: [String],
    remoteOnly: { type: Boolean, default: false }
  },
  notificationSettings: {
    emailDailyDigest: { type: Boolean, default: true },
    emailWeeklyReport: { type: Boolean, default: true },
    emailCareerAlerts: { type: Boolean, default: true }
  },
  createdAt: {
    type: Date,
    default: Date.now
  }
});

// Hash password before saving
userSchema.pre('save', async function(next) {
  if (!this.isModified('password')) return next();
  this.password = await bcrypt.hash(this.password, 12);
  next();
});

// Compare password method
userSchema.methods.comparePassword = async function(candidatePassword) {
  return await bcrypt.compare(candidatePassword, this.password);
};

module.exports = mongoose.model('User', userSchema);