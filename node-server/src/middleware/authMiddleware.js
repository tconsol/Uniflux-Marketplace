import jwt from 'jsonwebtoken';
import { settings } from '../config/settings.js';

export function authenticate(req, res, next) {
  const authHeader = req.headers['authorization'];
  if (!authHeader || !authHeader.startsWith('Bearer ')) {
    return res.status(401).json({ detail: 'Missing or invalid Authorization header' });
  }

  const token = authHeader.split(' ')[1];

  try {
    const payload = jwt.verify(token, settings.JWT_SECRET, {
      algorithms: [settings.JWT_ALGORITHM],
    });

    const orgId = payload.orgId || '';
    if (!orgId) {
      return res.status(401).json({ detail: 'Token missing orgId claim' });
    }

    req.currentUser = {
      userId: payload.userId || payload.sub || '',
      email: payload.sub || '',
      userName: payload.name || payload.sub || '',
      orgId,
      role: (payload.role || 'EMPLOYEE').toUpperCase(),
      isManager: ['MANAGER', 'ADMIN', 'ORG_ADMIN'].includes((payload.role || '').toUpperCase()),
      isAdmin: ['ADMIN', 'ORG_ADMIN'].includes((payload.role || '').toUpperCase()),
    };

    next();
  } catch (err) {
    return res.status(401).json({ detail: `Invalid or expired token: ${err.message}` });
  }
}
