import { Router } from 'express';
import { authenticate } from '../middleware/authMiddleware.js';
import {
  startIndeedSchedulerForOrg,
  stopIndeedSchedulerForOrg,
  getIndeedSchedulerStatusForOrg,
} from '../services/indeedSchedulerService.js';

const router = Router();

router.get('/status', authenticate, async (req, res) => {
  try {
    res.json(await getIndeedSchedulerStatusForOrg(req.currentUser.orgId));
  } catch (err) {
    res.status(500).json({ detail: err.message });
  }
});

router.post('/start', authenticate, async (req, res) => {
  try {
    res.json(await startIndeedSchedulerForOrg(req.currentUser.orgId, req.body));
  } catch (err) {
    res.status(502).json({ detail: `Indeed scheduler start error: ${err.message}` });
  }
});

router.post('/stop', authenticate, async (req, res) => {
  try {
    res.json(await stopIndeedSchedulerForOrg(req.currentUser.orgId));
  } catch (err) {
    res.status(502).json({ detail: `Indeed scheduler stop error: ${err.message}` });
  }
});

export default router;
