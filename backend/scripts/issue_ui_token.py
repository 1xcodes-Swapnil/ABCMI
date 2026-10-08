"""Local operator utility: print a short-lived token for an existing meeting host.

Run privately in your terminal. Never commit its output or paste it into logs.
Requires the configured database and signing secret; grants no additional role.
"""
import argparse
import asyncio
from datetime import timedelta
import os
from pathlib import Path
import sys
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(DEBUG="false", LOG_LEVEL="CRITICAL")

async def main(meeting_id):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.infrastructure.database import init_database, close_database_connections
    from app.models.meeting import Meeting
    from app.models.user import User
    from app.core.security import create_access_token
    async with async_sessionmaker(init_database(), expire_on_commit=False)() as db:
        meeting = await db.get(Meeting, meeting_id)
        if not meeting or not meeting.host_id or not meeting.tenant_id:
            raise RuntimeError("Meeting has no existing authorized host/tenant")
        user = await db.get(User, meeting.host_id)
        if not user or not user.is_active:
            raise RuntimeError("Meeting host is not an active account")
        token = create_access_token(data={"sub":str(user.id), "role":user.role,
            "tenant_id":meeting.tenant_id, "email":user.email}, expires_delta=timedelta(minutes=60))
        print(token)
    await close_database_connections()

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--meeting-id', type=uuid.UUID, required=True)
    asyncio.run(main(parser.parse_args().meeting_id))
