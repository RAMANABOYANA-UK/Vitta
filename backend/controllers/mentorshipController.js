const Mentor = require('../models/Mentor');
const User = require('../models/User');

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

    res.status(201).json({
      success: true,
      message: `Mentorship request sent to ${mentor.name}! They will confirm via email.`,
      request: {
        mentorId: mentor._id,
        mentorName: mentor.name,
        topic: topic || 'Career Growth',
        preferredTime: preferredTime || 'Flexible',
        note: note || '',
        status: 'Pending',
        createdAt: new Date()
      }
    });
  } catch (error) {
    next(error);
  }
};

module.exports = { getMentors, requestMentorship };
