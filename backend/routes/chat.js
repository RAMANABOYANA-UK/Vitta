const express = require('express');
const router = express.Router();
const { startSession, resumeSession, endSession, deleteSession, sendMessage, getHistory } = require('../controllers/chatController');
const { protect } = require('../middleware/auth');

router.post('/session', protect, startSession);
router.get('/session', protect, resumeSession);
router.post('/message', protect, sendMessage);
router.get('/history', protect, getHistory);
router.post('/session/:id/end', protect, endSession);
router.delete('/session/:id', protect, deleteSession);

module.exports = router;
