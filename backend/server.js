const express = require('express');
const mongoose = require('mongoose');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const dotenv = require('dotenv');

dotenv.config();

const connectDB = require('./config/db');
const errorHandler = require('./middleware/errorHandler');

// Import routes
const authRoutes = require('./routes/auth');
const careerRoutes = require('./routes/career');
const wellnessRoutes = require('./routes/wellness');
const chatRoutes = require('./routes/chat');
const opportunitiesRoutes = require('./routes/opportunities');
const dashboardRoutes = require('./routes/dashboard');
const mentorshipRoutes = require('./routes/mentorship');

const app = express();

// Allowed origins: production CLIENT_URL + any localhost/127.0.0.1 dev origin + null (file://)
const allowedOrigins = new Set([
  process.env.CLIENT_URL || 'http://localhost:8080',
  'http://localhost:8080',
  'http://127.0.0.1:8080',
  'http://localhost:5501',
  'http://127.0.0.1:5501',
  'http://localhost:3000',
  'http://127.0.0.1:3000'
]);

const corsOptions = {
  origin(origin, callback) {
    // Allow requests with no origin (server-to-server, curl, health checks)
    if (!origin) return callback(null, true);
    // Allow file:// (origin === 'null') and any localhost / 127.0.0.1 port
    if (origin === 'null') return callback(null, true);
    try {
      const { hostname, port } = new URL(origin);
      const isLocalhost =
        hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1';
      if (isLocalhost || allowedOrigins.has(origin)) {
        return callback(null, true);
      }
    } catch {
      // fall through to default rejection
    }
    callback(new Error('Not allowed by CORS'));
  },
  credentials: true
};

// Middleware
app.use(helmet({ crossOriginResourcePolicy: { policy: 'cross-origin' } }));
app.use(cors(corsOptions));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));
app.use(morgan('dev'));

// Health check - works even without DB
app.get('/api/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    message: 'Aviraa API is running',
    mongodb: mongoose.connection.readyState === 1 ? 'connected' : 'disconnected',
    timestamp: new Date().toISOString()
  });
});

// Test route
app.get('/api/test', (req, res) => {
  res.json({ message: 'Backend is working!' });
});

// Mount routes
app.use('/api/auth', authRoutes);
app.use('/api/career', careerRoutes);
app.use('/api/wellness', wellnessRoutes);
app.use('/api/chat', chatRoutes);
app.use('/api/opportunities', opportunitiesRoutes);
app.use('/api/dashboard', dashboardRoutes);
app.use('/api/mentorship', mentorshipRoutes);

// 404 handler
app.use((req, res) => {
  res.status(404).json({ message: `Route not found: ${req.originalUrl}` });
});

// Error handler
app.use(errorHandler);

// Connect to MongoDB
connectDB();

const PORT = process.env.PORT || 5000;
app.listen(PORT, () => {
  console.log(`🚀 Server running on http://localhost:${PORT}`);
  console.log(`📡 Health check: http://localhost:${PORT}/api/health`);
});