import random
import time as _time


# Realistic weather data pools
_CONDITIONS = [
    {"desc": "Clear sky", "icon": "sunny", "wind_mph": 5},
    {"desc": "Partly cloudy", "icon": "partly_cloudy", "wind_mph": 8},
    {"desc": "Overcast", "icon": "cloudy", "wind_mph": 12},
    {"desc": "Light rain", "icon": "rainy", "wind_mph": 10},
    {"desc": "Sunny", "icon": "sunny", "wind_mph": 3},
]

_ARTISTS = {
    "jazz": ["Miles Davis", "John Coltrane", "Thelonious Monk", "Bill Evans"],
    "lofi": ["Lofi Girl", "Chillhop", "Kupla", "Idealism"],
    "rock": ["Led Zeppelin", "Pink Floyd", "Arctic Monkeys", "Radiohead"],
    "pop": ["Dua Lipa", "The Weeknd", "Harry Styles", "Billie Eilish"],
    "classical": ["Chopin", "Debussy", "Bach", "Beethoven"],
}

_SONGS = {
    "jazz": ["So What", "Blue in Green", "Take Five", "Autumn Leaves"],
    "lofi": ["Cozy Morning", "Rainy Days", "Midnight Study", "Sunday Vibes"],
    "rock": ["Bohemian Rhapsody", "Stairway to Heaven", "Creep", "Do I Wanna Know"],
    "pop": ["Levitating", "Blinding Lights", "Watermelon Sugar", "Bad Guy"],
    "classical": ["Nocturne Op. 9", "Clair de Lune", "Cello Suite No. 1", "Moonlight Sonata"],
}

_CONTACTS = [
    {"name": "Alex Johnson", "phone": "+1 (415) 555-0142", "email": "alex.j@email.com"},
    {"name": "Sarah Chen", "phone": "+1 (650) 555-0198", "email": "sarah.c@email.com"},
    {"name": "Mike Rivera", "phone": "+1 (510) 555-0267", "email": "mike.r@email.com"},
]


def get_weather(location):
    cond = random.choice(_CONDITIONS)
    temp = random.randint(48, 88)
    return {
        "location": location,
        "temperature": f"{temp}\u00b0F",
        "feels_like": f"{temp + random.randint(-3, 3)}\u00b0F",
        "condition": cond["desc"],
        "humidity": f"{random.randint(35, 80)}%",
        "wind": f"{cond['wind_mph']} mph",
        "summary": f"{cond['desc']}, {temp}\u00b0F in {location}",
    }


def send_message(recipient, message):
    return {
        "status": "delivered",
        "to": recipient,
        "message": message,
        "timestamp": _time.strftime("%I:%M %p"),
        "summary": f"Message sent to {recipient}",
    }


def set_alarm(hour, minute):
    period = "AM" if hour < 12 else "PM"
    display_hour = hour if hour <= 12 else hour - 12
    if display_hour == 0:
        display_hour = 12
    return {
        "status": "set",
        "time": f"{display_hour}:{minute:02d} {period}",
        "summary": f"Alarm set for {display_hour}:{minute:02d} {period}",
    }


def set_timer(minutes):
    return {
        "status": "running",
        "duration": f"{minutes} min",
        "ends_at": _time.strftime("%I:%M %p", _time.localtime(_time.time() + minutes * 60)),
        "summary": f"Timer started \u2014 {minutes} min",
    }


def play_music(song):
    # Try to match genre
    song_lower = song.lower()
    genre = None
    for g in _ARTISTS:
        if g in song_lower:
            genre = g
            break
    if not genre:
        genre = random.choice(list(_ARTISTS.keys()))

    artist = random.choice(_ARTISTS[genre])
    track = random.choice(_SONGS[genre])
    return {
        "status": "playing",
        "track": track,
        "artist": artist,
        "source": song,
        "summary": f"Playing \"{track}\" by {artist}",
    }


def create_reminder(title, time):
    return {
        "status": "created",
        "title": title,
        "time": time,
        "summary": f"Reminder: {title} at {time}",
    }


def search_contacts(query):
    # Return a "matching" contact
    contact = random.choice(_CONTACTS)
    return {
        "status": "found",
        "query": query,
        "match": contact["name"],
        "phone": contact["phone"],
        "summary": f"Found {contact['name']} \u2014 {contact['phone']}",
    }
