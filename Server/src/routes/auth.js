// routes/auth.js
const { Router } = require('express');
const jwt = require('jsonwebtoken');
const { OAuth2Client } = require('google-auth-library');
const User = require('../models/user');

const router = Router();
const googleClient = new OAuth2Client(process.env.GOOGLE_CLIENT_ID);

router.post('/google', async (req, res, next) => {
  try {
    const { idToken } = req.body;
    if (!idToken) return res.status(400).json({ ok: false, error: 'Missing idToken' });

    const ticket = await googleClient.verifyIdToken({
      idToken,
      audience: process.env.GOOGLE_CLIENT_ID,
    });

    const payload = ticket.getPayload(); // sub, email, name, picture, email_verified, exp, aud, iss
    if (!payload.email_verified) {
      return res.status(401).json({ ok: false, error: 'Email not verified by Google' });
    }

    // Upsert user
    const { sub: googleId, email, name, picture } = payload;
    const user = await User.findOneAndUpdate(
      { googleId },
      { googleId, email, name, picture },
      { new: true, upsert: true, setDefaultsOnInsert: true }
    );

    // Issue your app token (JWT)
    const token = jwt.sign(
      { sub: user._id.toString(), googleId: user.googleId },
      process.env.JWT_SECRET,
      { expiresIn: '30d' }
    );

    res.json({
      ok: true,
      token,
      user: { id: user._id, email: user.email, name: user.name, picture: user.picture },
    });
  } catch (err) {
    next(err);
  }
});

router.get('/me', auth, async (req, res, next) => {
  try {
    // req.user.sub came from jwt.sign(...) when you created the token
    const user = await User.findById(req.user.sub).lean();

    if (!user) {
      return res.status(404).json({ ok: false, error: "User not found" });
    }

    res.json({
      ok: true,
      user: {
        id: user._id,
        email: user.email,
        name: user.name,
        picture: user.picture
      }
    });
  } catch (err) {
    next(err);
  }
});


function auth(req, res, next) {
  const hdr = req.headers.authorization || '';
  const token = hdr.startsWith('Bearer ') ? hdr.slice(7) : null;
  if (!token) return res.status(401).json({ ok: false, error: 'No token' });
  try {
    req.user = jwt.verify(token, process.env.JWT_SECRET);
    next();
  } catch {
    res.status(401).json({ ok: false, error: 'Invalid token' });
  }
};

module.exports = { router, auth };
