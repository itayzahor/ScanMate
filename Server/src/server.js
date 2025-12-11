require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const { connectDB } = require('../setup/db');
const routes = require('./routes');

const app = express();

// middleware
app.use(helmet());
app.use(cors());
app.use(express.json({ limit: '1mb' }));
app.use(morgan('dev'));

// routes
app.use('/api', routes);

// 404 handler
app.use((req, res, next) => {
  res.status(404).json({ ok: false, error: 'Not Found' });
});

// error handler
app.use((err, req, res, next) => {
  console.error(err);
  const status = err.status || 500;
  res.status(status).json({ ok: false, error: err.message || 'Server Error' });
});

// start
const PORT = process.env.PORT || 4000;
connectDB()
  .then(() => {
    app.listen(PORT, () => console.log(`API on http://localhost:${PORT}`));
  })
  .catch((e) => {
    console.error('Failed to connect DB:', e);
    process.exit(1);
  });
