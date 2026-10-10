-- Names are lookup hints, not canonical identity. Multiple entities may share a
-- normalized name; callers must receive an ambiguous result instead of merging.
DROP INDEX IF EXISTS canonical.entities_scoped_name_unique;
