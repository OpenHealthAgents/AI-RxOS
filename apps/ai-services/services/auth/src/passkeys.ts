import { dbPool } from "./auth.js";

export type PasskeyDevice = {
  id: string;
  accountId: string;
  providerId?: string;
  accountIdentifier?: string;
  name?: string;
  lastUsedAt?: string | null;
  revokedAt?: string | null;
  createdAt?: string;
};

export async function listPasskeysForUser(userId: string): Promise<PasskeyDevice[]> {
  const res = await dbPool.query(
    `SELECT pd.id, pd.account_id AS "accountId", a.provider_id AS "providerId", a.account_id AS "accountIdentifier", pd.name, pd.last_used_at AS "lastUsedAt", pd.revoked_at AS "revokedAt", pd.created_at AS "createdAt"
     FROM passkey_device pd
     JOIN account a ON a.id = pd.account_id
     WHERE a.user_id = $1 AND a.provider_id ILIKE 'passkey%'
     ORDER BY pd.created_at DESC`,
    [userId]
  );
  return res.rows as PasskeyDevice[];
}

export async function getPasskeyDevice(deviceId: string): Promise<PasskeyDevice | null> {
  const res = await dbPool.query(
    `SELECT pd.id, pd.account_id AS "accountId", a.provider_id AS "providerId", a.account_id AS "accountIdentifier", pd.name, pd.last_used_at AS "lastUsedAt", pd.revoked_at AS "revokedAt", pd.created_at AS "createdAt"
     FROM passkey_device pd JOIN account a ON a.id = pd.account_id WHERE pd.id = $1 LIMIT 1`,
    [deviceId]
  );
  return res.rowCount ? (res.rows[0] as PasskeyDevice) : null;
}

export async function renamePasskey(deviceId: string, userId: string, newName: string): Promise<boolean> {
  // Ensure user owns the device
  const res = await dbPool.query(
    `UPDATE passkey_device pd SET name = $1, updated_at = NOW()
     FROM account a WHERE pd.account_id = a.id AND pd.id = $2 AND a.user_id = $3 RETURNING pd.id`,
    [newName, deviceId, userId]
  );
  return (res.rowCount ?? 0) > 0;
}

export async function revokePasskey(deviceId: string, userIdOrNull: string | null, isAdmin = false): Promise<boolean> {
  if (isAdmin) {
    const res = await dbPool.query(`UPDATE passkey_device SET revoked_at = NOW(), updated_at = NOW() WHERE id = $1 RETURNING id`, [deviceId]);
    return (res.rowCount ?? 0) > 0;
  }
  const res = await dbPool.query(
    `UPDATE passkey_device pd SET revoked_at = NOW(), updated_at = NOW()
     FROM account a WHERE pd.account_id = a.id AND pd.id = $1 AND a.user_id = $2 RETURNING pd.id`,
    [deviceId, userIdOrNull]
  );
  return (res.rowCount ?? 0) > 0;
}

export async function recordPasskeyUse(deviceId: string): Promise<void> {
  await dbPool.query(`UPDATE passkey_device SET last_used_at = NOW(), updated_at = NOW() WHERE id = $1`, [deviceId]);
}

export async function listPasskeysForOrganization(organizationId: string): Promise<PasskeyDevice[]> {
  const res = await dbPool.query(
    `SELECT pd.id, pd.account_id AS "accountId", a.provider_id AS "providerId", a.account_id AS "accountIdentifier", pd.name, pd.last_used_at AS "lastUsedAt", pd.revoked_at AS "revokedAt", pd.created_at AS "createdAt"
     FROM passkey_device pd
     JOIN account a ON a.id = pd.account_id
     JOIN "user" u ON u.id = a.user_id
     JOIN member m ON m.user_id = u.id
     WHERE m.organization_id = $1 AND a.provider_id ILIKE 'passkey%'
     ORDER BY pd.created_at DESC`,
    [organizationId]
  );
  return res.rows as PasskeyDevice[];
}
