from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.keitaro.client import KeitaroClient


def get_keitaro(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[KeitaroClient]:
    client = KeitaroClient(settings)
    try:
        yield client
    finally:
        client.close()


DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
KeitaroDep = Annotated[KeitaroClient, Depends(get_keitaro)]
