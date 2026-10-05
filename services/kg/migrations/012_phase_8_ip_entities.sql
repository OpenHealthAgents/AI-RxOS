ALTER TABLE canonical.entities
    DROP CONSTRAINT IF EXISTS entities_entity_type_check;

ALTER TABLE canonical.entities
    ADD CONSTRAINT entities_entity_type_check CHECK (entity_type IN (
        'therapeutic_asset', 'target', 'disease', 'indication', 'biomarker',
        'company', 'clinical_trial', 'publication', 'patent', 'patent_family',
        'licensing_event', 'regulatory_event', 'mechanism', 'combination',
        'resistance_mechanism'
    ));

CREATE INDEX IF NOT EXISTS canonical_ip_entity_type_created_idx
    ON canonical.entities (entity_type, created_at DESC)
    WHERE entity_type IN ('patent', 'patent_family', 'licensing_event');
