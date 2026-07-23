import { describe, it, expect } from 'vitest';
import { hasRole } from './rbac.js';

describe('RBAC helper', ()=>{
  it('detects role presence', ()=>{
    expect(hasRole(['admin','owner'], 'owner')).toBe(true);
    expect(hasRole(['member'], ['owner','admin'])).toBe(false);
  });
});
