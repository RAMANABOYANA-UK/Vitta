const express = require('express');
const router = express.Router();
const { getMentors, requestMentorship } = require('../controllers/mentorshipController');
const { protect } = require('../middleware/auth');

router.get('/', protect, getMentors);
router.post('/:id/request', protect, requestMentorship);

module.exports = router;
