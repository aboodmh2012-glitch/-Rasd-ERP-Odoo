"""Shared fixtures for helpdesk_community_pro tests."""


def make_mon_fri_calendar(env, name="Mon-Fri 9-17"):
    """A Mon-Fri 9-17 UTC working calendar, for SLA deadline-math tests."""
    return env["resource.calendar"].create(
        {
            "name": name,
            "tz": "UTC",
            "attendance_ids": [
                (
                    0,
                    0,
                    {
                        "name": f"Day {day}",
                        "dayofweek": str(day),
                        "hour_from": 9,
                        "hour_to": 17,
                        "day_period": "morning",
                    },
                )
                for day in range(5)
            ],
        }
    )
