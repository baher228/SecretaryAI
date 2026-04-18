import asyncio
from datetime import datetime, timedelta
from db.session import AsyncSessionLocal, init_db
from db.models import Call, Task, Contact, UserProfile, StandingInstruction


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
        s.add(UserProfile(
            full_name="Vladimir Sukhachyov",
            role="Founder, VELURO",
            timezone="Europe/London",
            working_hours="10:00-19:00 Mon-Fri",
            preferred_language="en",
            communication_style="Direct and concise. Skip pleasantries. Ask clarifying questions before assuming.",
        ))
        s.add_all([
            Contact(
                name="Maria Lopez",
                phone_number="+447700900123",
                company="Lopez Capital",
                role="Investment Partner",
                notes="Handles Q2 budget review. Prefers email for documents.",
            ),
            Contact(
                name="John Chen",
                phone_number="+447700900456",
                company="Chen & Co",
                role="Client lead",
                notes="Reschedules frequently. Confirm meetings 24h in advance.",
            ),
        ])
        s.add_all([
            StandingInstruction(
                instruction="Never disclose the owner's personal phone number or home address to callers.",
                priority=100,
            ),
            StandingInstruction(
                instruction="If a caller claims urgency, ask for the specific deadline and reason before escalating.",
                priority=50,
            ),
        ])
        await s.commit()
    print("Seeded 3 calls, 2 tasks, 1 profile, 2 contacts, 2 standing instructions.")


if __name__ == "__main__":
    asyncio.run(main())
