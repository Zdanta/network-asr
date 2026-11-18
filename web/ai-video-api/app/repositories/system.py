from sqlalchemy import select

from app.models.system import SysConfig
from app.repositories.base import BaseRepository


class SysConfigRepository(BaseRepository[SysConfig]):
    model = SysConfig

    def get_by_key(self, config_key: str) -> SysConfig | None:
        return self.session.execute(
            select(SysConfig).where(SysConfig.config_key == config_key, SysConfig.deleted == 0)
        ).scalar_one_or_none()
