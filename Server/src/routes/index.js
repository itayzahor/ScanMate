const { Router } = require('express');
const { router: authRouter } = require('./auth');

const router = Router();

// mount Google auth routes
router.use('/auth', authRouter);

module.exports = router;
