import sys
import re
import yaml
from datetime import timedelta, datetime
from icalendar import Calendar, Event


class TrainingEvent:
    def __init__(self, date, title, desc):
        self.date = date
        self.title = title
        self.desc = desc

    def __str__(self):
        return "(" + str(self.date) + ": " + self.title + ", " + str(self.desc) + ")"


def bail(msg):
    print("[ERROR]: " + msg)
    sys.exit(1)


def get_weekday_ordinal(weekday_str):
    if weekday_str is None:
        # Deafult is Monday
        return 0
    elif weekday_str.casefold()[:3] == "Mon".casefold():  # YAML Plan Keyword
        return 0
    elif weekday_str.casefold()[:3] == "Tue".casefold():  # YAML Plan Keyword
        return 1
    elif weekday_str.casefold()[:3] == "Wed".casefold():  # YAML Plan Keyword
        return 2
    elif weekday_str.casefold()[:3] == "Thu".casefold():  # YAML Plan Keyword
        return 3
    elif weekday_str.casefold()[:3] == "Fri".casefold():  # YAML Plan Keyword
        return 4
    elif weekday_str.casefold()[:3] == "Sat".casefold():  # YAML Plan Keyword
        return 5
    elif weekday_str.casefold()[:3] == "Sun".casefold():  # YAML Plan Keyword
        return 6
    else:
        bail("Unknown word in weekly start date: " + weekday_str)


def get_week_schedule(schedule):
    schedule_length = 0
    running_today = []
    events = []
    for event in schedule:
        if event.casefold() == "rest".casefold():  # YAML Plan Keyword
            running_today.append(False)
        else:
            schedule_length += 1
            running_today.append(True)
            events.append(event)

    return schedule_length, running_today, events


def get_event_desc(plan_name, current_week, current_date, race_date, event_desc):
    checked_event_desc = event_desc + "\n\n" if event_desc is not None else ""

    # Calculate the time-to-race
    delta_until_race = race_date - current_date
    weeks_delta = delta_until_race.days // 7
    days_remainder = delta_until_race.days % 7

    time_to_race = ""

    if weeks_delta > 1:
        time_to_race += "{} weeks".format(weeks_delta)
    elif weeks_delta == 1:
        time_to_race += "1 week"

    if days_remainder > 1:
        time_to_race += ", " if time_to_race else ""
        time_to_race += "{} days".format(days_remainder)
    elif days_remainder == 1:
        time_to_race += ", " if time_to_race else ""
        time_to_race += "1 day"
    else:
        time_to_race += "0 days" if not time_to_race else ""

    desc = ("{}"
            "Week {}\n"
            "{} until race (as of {})\n"
            "{} / Training Calendar Generator")

    return desc.format(checked_event_desc, current_week, time_to_race, current_date, plan_name)


def collect_events(document):
    # Get the basic info
    plan_name = document["Event"]  # YAML Plan Keyword
    race_date = document["Race Date"]  # YAML Plan Keyword
    start_day = get_weekday_ordinal(document.get("Weekly Start Day"))  # YAML Plan Keyword

    # Build the standard weekly schedules
    weekly_schedules = {}
    for schedule in document["Weekly Schedules"]:  # YAML Plan Keyword
        (schedule_length, parsed_schedule, _) = get_week_schedule(schedule)
        weekly_schedules[schedule_length] = parsed_schedule

    # Setup the date cursor
    training_plan = document["Training Plan"]  # YAML Plan Keyword

    # Assume the race date occurs during the last week (i.e., assume recovery weeks are omitted).
    date_cursor = race_date - timedelta(days=(race_date.weekday() + start_day))
    date_cursor = date_cursor - timedelta(weeks=(len(training_plan) - 1))

    # Collect the events
    events = []
    for week in training_plan:
        if week == "skip":
            date_cursor = date_cursor + timedelta(weeks=1)
            continue

        if len(week) in weekly_schedules:
            week_events = week
            schedule = weekly_schedules[len(week)]
        else:
            (_, schedule, week_events) = get_week_schedule(week)

        week_itr = iter(week_events)
        for day in schedule:
            if day:
                event = next(week_itr)
                if date_cursor > race_date:
                    # Ignore everything on or after the race date
                    pass
                elif date_cursor == race_date:
                    events.append(TrainingEvent(date_cursor,
                                                "Race Day: " + plan_name,
                                                get_event_desc(plan_name, training_plan.index(week) + 1, date_cursor, race_date, None)))
                elif isinstance(event, str):
                    events.append(TrainingEvent(date_cursor,
                                                event + " Run",
                                                get_event_desc(plan_name, training_plan.index(week) + 1, date_cursor, race_date, None)))
                elif isinstance(event, dict) and len(event) == 2:
                    events.append(TrainingEvent(date_cursor,
                                                event[0] + " Run",
                                                get_event_desc(plan_name, training_plan.index(week) + 1, date_cursor, race_date, event[1])))
                else:
                    bail("Unknown object in training plan: " + str(event))

            date_cursor = date_cursor + timedelta(days=1)

    return plan_name, events


def get_icalendar_contents(_, training_plan):
    cal = Calendar()

    # For RFC compliance
    cal.add("prodid", "-//tpsavard.net//training_calendar_generator//EN")
    cal.add("version", "2.0")

    # Add the events
    for event in training_plan:
        ical_event = Event()

        ical_event.add("summary", event.title)
        ical_event.add("description", event.desc)
        ical_event.add("dtstart", event.date)
        ical_event.add("dtend", event.date + timedelta(days=1))
        ical_event.add("dtstamp", datetime.now())

        cal.add_component(ical_event)

    return cal.to_ical()

# ~


if __name__ == "__main__":
    # Read args, read the YAML file
    if not len(sys.argv) == 2:
        bail("Usage: training_calendar_generator.py [training plan file]")

    with open(sys.argv[1], "r") as file:
        training_plan_document = yaml.safe_load(file)

    # Parse the file contents
    (plan_name, training_plan) = collect_events(training_plan_document)

    # Output the read events, for sanity
    print(plan_name)
    print(str(len(training_plan)) + " events found")
    for event in training_plan:
        print(event)

    # Compile the icalendar file contents
    ical = get_icalendar_contents(plan_name, training_plan)

    # Write out the file
    ext_re = re.compile("\.\w*$")
    ical_filename = ext_re.sub(".ics", sys.argv[1])
    with open(ical_filename, "wb") as file:
        file.write(ical)
        