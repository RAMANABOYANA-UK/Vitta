const express = require('express');
const router = express.Router();
const { getCareer, updateSkills, addGoal, analyzeResume, getInterviewQuestion, getCareerInsights, getLearningPath, exportCareerPlan } = require('../controllers/careerController');
const { protect } = require('../middleware/auth');

router.get('/', protect, getCareer);
router.put('/skills', protect, updateSkills);
router.post('/goals', protect, addGoal);
router.post('/analyze-resume', protect, analyzeResume);
router.post('/interview-prep', protect, getInterviewQuestion);
router.get('/insights', protect, getCareerInsights);
router.get('/learning-path', protect, getLearningPath);
router.get('/export-plan', protect, exportCareerPlan);

module.exports = router;
