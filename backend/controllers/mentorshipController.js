const Mentor = require('../models/Mentor');
const User = require('../models/User');
const MentorshipRequest = require('../models/MentorshipRequest');
const { deliverEmail } = require('../utils/emailSender');

// Default initial mentors dataset if DB is empty
const DEFAULT_MENTORS = [
  {
    name: 'Ananya Sharma',
    title: 'VP of Engineering',
    company: 'TechCorp International',
    category: 'Tech',
    expertise: ['System Design', 'Engineering Leadership', 'Cloud Architecture', 'Python'],
    bio: '14+ years in tech leadership. Passionate about empowering women in software engineering and executive leadership.',
    rating: 4.9,
    sessionCount: 68,
    availability: 'Tuesdays & Thursdays',
    hourlyRate: 'Free (Community)',
    matchScore: 95
  },
  {
    name: 'Dr. Priya Nair',
    title: 'Lead Wellness & Mindfulness Coach',
    company: 'Holistic Health Institute',
    category: 'Wellness',
    expertise: ['Burnout Prevention', 'Work-Life Balance', 'Cycle Synchronization', 'Stress Management'],
    bio: 'Integrative health practitioner supporting professional women in overcoming workplace burnout and hormonal balance.',
    rating: 5.0,
    sessionCount: 112,
    availability: 'Available weekends',
    hourlyRate: 'Free (Community)',
    matchScore: 91
  },
  {
    name: 'Rhea Kapoor',
    title: 'Head of Product Strategy',
    company: 'Fintech Surge',
    category: 'Career',
    expertise: ['Product Management', 'Salary Negotiation', 'Career Pivot', 'Interview Prep'],
    bio: 'Product leader who scaled 3 startups. Specializes in helping mid-level managers break into Director & VP roles.',
    rating: 4.8,
    sessionCount: 54,
    availability: 'Wednesdays & Fridays',
    hourlyRate: 'Free (Community)',
    matchScore: 88
  },
  {
    name: 'Meera Sengupta',
    title: 'Founder & CEO',
    company: 'EmpowerVentures',
    category: 'Entrepreneurship',
    expertise: ['Fundraising', 'Pitch Deck', 'Business Model', 'Networking'],
    bio: 'Serial entrepreneur & angel investor. Guided over 40 female-led startups from pre-seed to Series A.',
    rating: 4.9,
    sessionCount: 79,
    availability: 'Mondays',
    hourlyRate: 'Free (Community)',
    matchScore: 85
  }
];

// Seed mentors if database collection is empty
const seedMentorsIfEmpty = async () => {
  try {
    const count = await Mentor.countDocuments();
    if (count === 0) {
      await Mentor.insertMany(DEFAULT_MENTORS);
      console.log('🌱 Seeded 4 default mentors into database.');
    }
  } catch (err) {
    console.warn('Mentor seeding warning:', err.message);
  }
};

// @desc    Get mentors list with match scoring
// @route   GET /api/mentorship
const getMentors = async (req, res, next) => {
  try {
    await seedMentorsIfEmpty();
    const { category, search } = req.query;
    let filter = {};

    if (category && category !== 'All') {
      filter.category = category;
    }

    if (search) {
      filter.$or = [
        { name: { $regex: search, $options: 'i' } },
        { title: { $regex: search, $options: 'i' } },
        { company: { $regex: search, $options: 'i' } },
        { expertise: { $elemMatch: { $regex: search, $options: 'i' } } }
      ];
    }

    let mentors = await Mentor.find(filter).sort({ rating: -1 });

    // Calculate match score based on user skills
    const user = await User.findById(req.user._id);
    const userSkills = (user?.skills || []).map(s => String(s.name || s).toLowerCase());

    const scoredMentors = mentors.map(m => {
      const obj = m.toObject();
      let matchCount = 0;
      (obj.expertise || []).forEach(e => {
        if (userSkills.some(us => e.toLowerCase().includes(us) || us.includes(e.toLowerCase()))) {
          matchCount++;
        }
      });
      obj.computedMatchScore = Math.min(99, Math.max(70, 75 + matchCount * 8));
      return obj;
    });

    res.json(scoredMentors);
  } catch (error) {
    next(error);
  }
};

// @desc    Request 1-on-1 mentorship session
// @route   POST /api/mentorship/:id/request
const requestMentorship = async (req, res, next) => {
  try {
    const mentor = await Mentor.findById(req.params.id);
    if (!mentor) {
      return res.status(404).json({ message: 'Mentor not found' });
    }

    const { note, topic, preferredTime } = req.body;
    const user = await User.findById(req.user._id).select('name email');

    // Prevent duplicate pending request
    const existing = await MentorshipRequest.findOne({
      user: req.user._id,
      mentor: mentor._id,
      status: 'pending'
    });

    if (existing) {
      return res.status(200).json({
        success: true,
        message: 'You already have a pending request with this mentor.',
        request: existing
      });
    }

    const request = await MentorshipRequest.create({
      user: req.user._id,
      mentor: mentor._id,
      topic: topic || 'Career Growth',
      preferredTime: preferredTime || 'Flexible',
      note: note || '',
      status: 'pending'
    });

    // Email to user (confirmation)
    const userSubject = `🌱 Mentorship request sent to ${mentor.name}`;
    const userHtml = `
      <div style="font-family:Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;padding:24px;">
        <h2 style="color:#b86b7d;">Request Submitted!</h2>
        <p>Hi ${user?.name || 'there'},</p>
        <p>Your mentorship request has been sent to <strong>${mentor.name}</strong> (${mentor.title}).</p>
        <ul>
          <li><strong>Topic:</strong> ${request.topic}</li>
          <li><strong>Preferred time:</strong> ${request.preferredTime}</li>
          <li><strong>Note:</strong> ${request.note || '—'}</li>
        </ul>
        <p>We will notify you when they respond.</p>
        <p>💜 Team Aviraa</p>
      </div>
    `;
    if (user?.email) {
      await deliverEmail(user.email, userSubject, userHtml);
    }

    // Log mentor notification (Mentor has no email field in the current model;
    // when a mentor email field is added, deliver here too).
    console.log(`📧 Mentorship request created: ${user?.name || 'user'} → ${mentor.name} | topic: ${request.topic}`);

    const populated = await MentorshipRequest.findById(request._id)
      .populate('mentor', 'name title company')
      .populate('user', 'name email');

    res.status(201).json({
      success: true,
      message: `Mentorship request sent to ${mentor.name}! You will receive a confirmation email.`,
      request: populated
    });
  } catch (error) {
    if (error.code === 11000) {
      return res.status(200).json({
        success: true,
        message: 'You already have a pending request with this mentor.'
      });
    }
    next(error);
  }
};

// @desc    Get current user's mentorship requests
// @route   GET /api/mentorship/requests/me
const getMyRequests = async (req, res, next) => {
  try {
    const requests = await MentorshipRequest.find({ user: req.user._id })
      .populate('mentor', 'name title company category expertise rating')
      .sort({ createdAt: -1 });

    res.json(requests);
  } catch (error) {
    next(error);
  }
};

// @desc    Update request status (for future mentor/admin panel)
// @route   PATCH /api/mentorship/requests/:id
const updateRequestStatus = async (req, res, next) => {
  try {
    const { status } = req.body;
    const allowed = ['pending', 'accepted', 'rejected', 'completed', 'cancelled'];
    if (!allowed.includes(status)) {
      return res.status(400).json({ message: 'Invalid status' });
    }

    const request = await MentorshipRequest.findOne({
      _id: req.params.id,
      user: req.user._id
    });

    if (!request) {
      return res.status(404).json({ message: 'Request not found' });
    }

    request.status = status;
    await request.save();

    res.json({ success: true, request });
  } catch (error) {
    next(error);
  }
};

module.exports = { getMentors, requestMentorship, getMyRequests, updateRequestStatus };
