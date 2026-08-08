const mongoose = require('mongoose');
const dotenv = require('dotenv');
const Opportunity = require('../models/Opportunity');

dotenv.config();

const opportunities = [
  {
    title: 'Senior Product Manager',
    type: 'job',
    company: 'Tech4Good',
    location: 'Remote-First · Bangalore',
    salary: '₹35L - 50L',
    description: 'Lead product strategy for flagship SaaS platform.',
    tags: ['Product', 'Leadership', 'Remote'],
    matchScore: 92,
    requirements: ['5+ years PM experience', 'SaaS background', 'Team leadership']
  },
  {
    title: 'AI Product Management Certificate',
    type: 'course',
    provider: 'Coursera · Stanford',
    duration: '6 weeks · Self-paced',
    description: 'Learn to build AI-powered products.',
    tags: ['AI/ML', 'Product', 'Certificate'],
    matchScore: 95
  },
  {
    title: 'Women in Product Mentorship',
    type: 'mentorship',
    provider: 'Aviraa Community',
    duration: '6-month program',
    description: 'Get matched with VP-level product leader.',
    tags: ['Mentorship', 'Leadership', 'Women'],
    matchScore: 90
  },
  {
    title: 'Product Strategy Consultant',
    type: 'freelance',
    company: 'EduSpark',
    location: 'Remote · 20 hrs/week',
    salary: '₹2L - 3L/month',
    description: 'Shape product strategy for Series A startup.',
    tags: ['Consulting', 'EdTech', 'Flexible'],
    matchScore: 85
  }
];

const seedDB = async () => {
  try {
    await mongoose.connect(process.env.MONGODB_URI);
    console.log('Connected to MongoDB');

    await Opportunity.deleteMany({});
    await Opportunity.insertMany(opportunities);
    
    console.log('✅ Database seeded with sample opportunities');
    process.exit(0);
  } catch (error) {
    console.error('Seeding error:', error);
    process.exit(1);
  }
};

seedDB();