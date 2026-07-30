from neo4j import AsyncDriver, AsyncGraphDatabase
from app.core.config import Settings

class Neo4jManager:
    def __init__(self):
        self.driver: AsyncDriver | None = None

    def init_driver(self, settings: Settings):
        self.driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password)
        )

    async def close(self):
        if self.driver:
            await self.driver.close()
            self.driver = None

    def get_session(self, database: str = "neo4j"):
        if not self.driver:
            raise RuntimeError("Neo4j driver is not initialized")
        return self.driver.session(database=database)

neo4j_manager = Neo4jManager()
