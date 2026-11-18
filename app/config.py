from dataclasses import dataclass
import os

from app import rulebook


@dataclass(frozen=True)
class Settings:
    db_path: str = "./data/grantalloc.db"
    rule_version: str = rulebook.CURRENT_RULE_VERSION
    timezone: str = "Asia/Shanghai"

    @classmethod
    def from_env(cls):
        return cls(db_path=os.getenv("DB_PATH", cls.db_path),
                   rule_version=rulebook.current_version())

