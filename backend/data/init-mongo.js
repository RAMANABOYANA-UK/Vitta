// Create application user
db = db.getSiblingDB('admin');

db.createUser({
  user: 'aviraa_user',
  pwd: 'AviraaUser2024!',
  roles: [
    {
      role: 'readWrite',
      db: 'aviraa'
    }
  ]
});

// Switch to application database
db = db.getSiblingDB('aviraa');

// Create collections
db.createCollection('users');
db.createCollection('careers');
db.createCollection('wellnesses');
db.createCollection('chats');
db.createCollection('opportunities');
db.createCollection('savedopportunities');

// Create indexes
db.users.createIndex({ email: 1 }, { unique: true });
db.careers.createIndex({ user: 1 });
db.wellnesses.createIndex({ user: 1 });
db.chats.createIndex({ user: 1, sessionStart: -1 });
db.opportunities.createIndex({ type: 1, isActive: 1 });
db.opportunities.createIndex({ tags: 1 });

// Insert sample opportunities
db.opportunities.insertMany([
  {
    title: 'Senior Product Manager',
    type: 'job',
    company: 'Tech4Good',
    location: 'Remote-First · Bangalore',
    salary: '₹35L - 50L',
    description: 'Lead product strategy for flagship SaaS platform. Women-led team with flexible hours.',
    tags: ['Product', 'Leadership', 'Remote'],
    matchScore: 92,
    isActive: true,
    postedDate: new Date(),
    createdAt: new Date()
  },
  {
    title: 'AI Product Management Certificate',
    type: 'course',
    provider: 'Coursera · Stanford',
    duration: '6 weeks · Self-paced',
    description: 'Learn to build and manage AI-powered products.',
    tags: ['AI/ML', 'Product', 'Certificate'],
    matchScore: 95,
    isActive: true,
    postedDate: new Date(),
    createdAt: new Date()
  },
  {
    title: 'Women in Product Mentorship',
    type: 'mentorship',
    provider: 'Aviraa Community',
    duration: '6-month program',
    description: 'Get matched with VP-level product leader.',
    tags: ['Mentorship', 'Leadership', 'Women'],
    matchScore: 90,
    isActive: true,
    postedDate: new Date(),
    createdAt: new Date()
  },
  {
    title: 'Product Strategy Consultant',
    type: 'freelance',
    company: 'EduSpark',
    location: 'Remote · 20 hrs/week',
    salary: '₹2L - 3L/month',
    description: 'Shape product strategy for Series A EdTech startup.',
    tags: ['Consulting', 'EdTech', 'Flexible'],
    matchScore: 85,
    isActive: true,
    postedDate: new Date(),
    createdAt: new Date()
  },
  {
    title: 'Product Lead - Growth',
    type: 'job',
    company: 'FinVerse',
    location: 'Hybrid · Mumbai',
    salary: '₹40L - 55L',
    description: 'Drive user acquisition and retention for payment products.',
    tags: ['Growth', 'FinTech', 'Strategy'],
    matchScore: 88,
    isActive: true,
    postedDate: new Date(),
    createdAt: new Date()
  }
]);

print('✅ Aviraa database initialized successfully');