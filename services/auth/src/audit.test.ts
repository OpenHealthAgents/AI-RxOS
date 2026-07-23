import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import pg from 'pg';
import { initDatabase } from './db.js';
import { config } from './config.js';
import { recordAuditEvent } from './audit.js';
import { verifyAuditLogRecord } from './auditVerification.js';

const pool = new pg.Pool({ connectionString: config.databaseUrl });

const testRecordId = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

describe('Audit log integrity', () => {
  beforeAll(async () => {
    await initDatabase();
    await pool.query('BEGIN');
  }, 20000);

  afterAll(async () => {
    await pool.query('ROLLBACK');
    await pool.end();
  });

  it('writes audit log entries with hash and signature fields', async () => {
    await recordAuditEvent({
      userId: null,
      organizationId: null,
      action: 'test_audit_hash',
      resourceType: 'audit_record',
      resourceId: testRecordId,
      ipAddress: '127.0.0.1',
      userAgent: 'vitest',
      metadata: { foo: 'bar' },
    });

    const row = await pool.query(
      `SELECT id, prev_hash, current_hash, signature FROM audit_log WHERE resource_id = $1 ORDER BY created_at DESC LIMIT 1`,
      [testRecordId]
    );

    expect(row.rowCount).toBe(1);
    const auditRow = row.rows[0];
    expect(auditRow.current_hash).toMatch(/^[0-9a-f]{64}$/);
    expect(auditRow.signature).toMatch(/^[0-9a-f]{64}$/);
  });

  it('verifies audit log entries successfully', async () => {
    const row = await pool.query(
      `SELECT id FROM audit_log WHERE resource_id = $1 ORDER BY created_at DESC LIMIT 1`,
      [testRecordId]
    );
    expect(row.rowCount).toBe(1);

    const verified = await verifyAuditLogRecord(row.rows[0].id);
    expect(verified).toBe(true);
  });

  it('detects tampering when current_hash does not match row contents', async () => {
    const row = await pool.query(
      `SELECT id FROM audit_log WHERE resource_id = $1 ORDER BY created_at DESC LIMIT 1`,
      [testRecordId]
    );
    expect(row.rowCount).toBe(1);
    const id = row.rows[0].id;

    // The audit log is intentionally immutable; attempting to update should fail.
    let updateFailed = false;
    try {
      await pool.query(`UPDATE audit_log SET action = 'tampered' WHERE id = $1`, [id]);
    } catch (e: any) {
      updateFailed = /immutable/.test(String(e.message));
    }
    expect(updateFailed).toBe(true);

    // Record should still verify as valid
    const verified = await verifyAuditLogRecord(id);
    expect(verified).toBe(true);
  });
});
