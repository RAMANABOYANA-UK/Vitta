const express = require('express');
const router = express.Router();
const { signup, login, getProfile, updateProfile, sendDigestEmail } = require('../controllers/authController');
const { protect } = require('../middleware/auth');

router.post('/signup', signup);
router.post('/login', login);
router.get('/profile', protect, getProfile);
router.put('/profile', protect, updateProfile);
router.post('/send-digest', protect, sendDigestEmail);

module.exports = router;