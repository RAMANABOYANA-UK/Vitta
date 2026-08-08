const express = require('express');
const router = express.Router();
const { getOpportunities, saveOpportunity, applyOpportunity } = require('../controllers/opportunityController');
const { protect } = require('../middleware/auth');

router.get('/', protect, getOpportunities);
router.post('/:id/save', protect, saveOpportunity);
router.post('/:id/apply', protect, applyOpportunity);

module.exports = router;