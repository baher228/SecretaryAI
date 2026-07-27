1. Keep Telegram as the single call/message channel for the current personal-use phase.
2. Track latency KPIs per call: answer time, first response time, and barge-in stop time.
3. Prioritize interruption-first behavior (stop assistant speech immediately when user speaks).
4. Run optional Telegram text bot in the same runtime for notifications and lightweight text commands.
5. Maintain RU/EN voice quality with concise interruption-aware prompt rules.
6. Keep deployment defaults production-safe while preserving hot-reload via compose dev profile.
