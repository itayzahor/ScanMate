// models/User.js
const { Schema, model } = require('mongoose');

const userSchema = new Schema({
  googleId: { type: String, index: true, unique: true, sparse: true },
  email: { type: String, index: true },
  name: String,
  picture: String,
}, { timestamps: true });

module.exports = model('User', userSchema);
