import { describe, it, expect } from 'vitest';
import { rateLimiter } from './rateLimit.js';

// We cannot easily run middleware fully without express, but validate that factory returns a function
describe('Rate limiter', ()=>{
  it('returns middleware function', ()=>{
    const mw = rateLimiter(5,60);
    expect(typeof mw).toBe('function');
  });
});
