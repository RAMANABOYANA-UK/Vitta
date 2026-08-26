const express = require('express');
const router = express.Router();
const {
  getMentors,
  requestMentorship,
  getMyRequests,
  updateRequestStatus
} = require('../controllers/mentorshipController');
const { protect } = require('../middleware/auth');

router.get('/', protect, getMentors);
router.post('/:id/request', protect, requestMentorship);
router.get('/requests/me', protect, getMyRequests);
router.patch('/requests/:id', protect, updateRequestStatus);

module.exports = router;
