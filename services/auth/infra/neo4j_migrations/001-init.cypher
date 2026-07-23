// Neo4j initial migration: basic permission relationships
CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (r:Resource) REQUIRE r.id IS UNIQUE;

// Example relationship: (u)-[:HAS_ACCESS {action:'read'}]->(r)

