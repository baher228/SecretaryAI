import asyncio
from datetime import datetime, timedelta
from db.session import AsyncSessionLocal, init_db
from db.models import Call, Task


async def main():
    await init_db()
    async with AsyncSessionLocal() as s:
        now = datetime.utcnow()
        s.add_all([
            Call(
                started_at=now - timedelta(days=1, hours=3),
                ended_at=now - timedelta(days=1, hours=2, minutes=45),
                caller_name="Maria Lopez",
                caller_number="+447700900123",
                summary="Discussed Q2 budget. She will send revised proposal by Friday.",
                transcript="Maria: Hi, I wanted to go over the Q2 numbers... [full transcript here]",
            ),
            Call(
                started_at=now - timedelta(days=3),
                ended_at=now - timedelta(days=3) + timedelta(minutes=8),
                caller_name="John Chen",
                caller_number="+447700900456",
                summary="Rescheduled Thursday meeting to Tuesday next week at 3pm.",
                transcript="John: Hey, I need to move our Thursday call...",
            ),
            Call(
                started_at=now - timedelta(days=5),
                caller_name="Unknown",
                caller_number="+447700900789",
                summary="Cold sales call from DataCorp. Declined politely.",
                transcript="Caller: Hi, I'm reaching out from DataCorp...",
            ),
        ])
        s.add_all([
            Task(description="Follow up with Maria on Q2 proposal", due_at=now + timedelta(days=2)),
            Task(description="Prepare slides for Tuesday meeting with John", due_at=now + timedelta(days=6)),
        ])
        await s.commit()
    print("Seeded 3 calls and 2 tasks.")


if __name__ == "__main__":
    asyncio.run(main())
