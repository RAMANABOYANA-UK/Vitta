const express = require('express');
const router = express.Router();
const { getWellness, logMood, logSleep, logWater, logExercise, logStress, logCycle, getHabits, logHabit, getWellnessStats } = require('../controllers/wellnessController');
const { protect } = require('../middleware/auth');

router.get('/', protect, getWellness);
router.get('/stats', protect, getWellnessStats);
router.get('/habits', protect, getHabits);
router.post('/mood', protect, logMood);
router.post('/sleep', protect, logSleep);
router.post('/water', protect, logWater);
router.post('/exercise', protect, logExercise);
router.post('/stress', protect, logStress);
router.post('/cycle', protect, logCycle);
router.post('/habits', protect, logHabit);

module.exports = router;
