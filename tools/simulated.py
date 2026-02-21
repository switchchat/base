import random


def get_weather(location):
    conditions = ["sunny", "cloudy", "rainy", "partly cloudy", "windy"]
    return {
        "location": location,
        "temperature_f": random.randint(45, 95),
        "condition": random.choice(conditions),
        "humidity": random.randint(30, 90),
    }


def send_message(recipient, message):
    return {"status": "sent", "recipient": recipient, "message": message}


def set_alarm(hour, minute):
    return {"status": "set", "hour": hour, "minute": minute}


def set_timer(minutes):
    return {"status": "started", "minutes": minutes}


def play_music(song):
    return {"status": "playing", "song": song}


def create_reminder(title, time):
    return {"status": "created", "title": title, "time": time}


def search_contacts(query):
    return {"status": "found", "query": query, "results": [f"{query} (Mobile)", f"{query} (Work)"]}
