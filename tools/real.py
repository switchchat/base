"""
Real tool implementations for macOS.
Uses AppleScript, system commands, and free APIs.
"""

import json
import subprocess
import threading
import time as _time
import urllib.request


# =====================================================================
# Weather — real data via wttr.in (free, no API key)
# =====================================================================
def get_weather(location):
    url = "https://wttr.in/{}?format=j1".format(location.replace(" ", "+"))
    last_err = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read())
            c = data["current_condition"][0]
            temp_f = c["temp_F"]
            desc = c["weatherDesc"][0]["value"]
            return {
                "location": location,
                "temperature": "{}°F".format(temp_f),
                "feels_like": "{}°F".format(c.get("FeelsLikeF", temp_f)),
                "condition": desc,
                "humidity": "{}%".format(c["humidity"]),
                "wind": "{} mph".format(c["windspeedMiles"]),
                "summary": "{}, {}°F in {}".format(desc, temp_f, location),
            }
        except Exception as e:
            last_err = e
            _time.sleep(0.5)
    return {"error": str(last_err), "summary": "Could not fetch weather for {}".format(location)}


# =====================================================================
# Play Music — opens Apple Music or Spotify
# =====================================================================
def play_music(song):
    try:
        # Check which music apps are running
        result = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to get name of every process'],
            capture_output=True, text=True, timeout=3,
        )
        apps = result.stdout.lower()

        if "spotify" in apps:
            subprocess.Popen(["open", "spotify:search:%s" % song])
            _time.sleep(1.5)
            subprocess.run([
                "osascript", "-e",
                'tell application "Spotify"\n'
                '  activate\n'
                '  play\n'
                'end tell',
            ], timeout=3)
            return {"status": "playing", "app": "Spotify", "query": song,
                    "summary": 'Playing "%s" on Spotify' % song}

        # Apple Music: try multiple search terms for better matching
        search_terms = [song]
        words = song.split()
        if len(words) > 1:
            search_terms.append(words[0])
            search_terms.append(" ".join(words[1:]))

        for term in search_terms:
            safe_term = term.replace('"', '\\"')
            search_script = '\n'.join([
                'tell application "Music"',
                '  activate',
                '  delay 0.5',
                '  set searchResults to search playlist "Library" for "%s" only songs' % safe_term,
                '  if (count of searchResults) > 0 then',
                '    play item 1 of searchResults',
                '    set trackName to name of item 1 of searchResults',
                '    set artistName to artist of item 1 of searchResults',
                '    return trackName & " by " & artistName',
                '  else',
                '    return "NOT_FOUND"',
                '  end if',
                'end tell',
            ])
            result = subprocess.run(
                ["osascript", "-e", search_script],
                capture_output=True, text=True, timeout=15,
            )
            output = result.stdout.strip()
            if result.stderr.strip():
                print("[play_music] stderr for '%s': %s" % (term, result.stderr.strip()))

            if output and output != "NOT_FOUND":
                return {"status": "playing", "app": "Apple Music", "query": song,
                        "now_playing": output,
                        "summary": "Now playing %s on Apple Music" % output}

        # Nothing found in library
        subprocess.Popen(["open", "https://music.apple.com/us/search?term=%s" %
            song.replace(" ", "+")])
        return {"status": "searching", "app": "Apple Music", "query": song,
                "summary": 'Searching "%s" on Apple Music (not in library)' % song}

    except Exception as e:
        return {"error": str(e), "summary": "Could not play music"}


# =====================================================================
# Timer — real countdown with macOS notification
# =====================================================================
def set_timer(minutes):
    ends_at = _time.strftime("%I:%M %p", _time.localtime(_time.time() + minutes * 60))

    def _timer():
        _time.sleep(minutes * 60)
        subprocess.run([
            "osascript", "-e",
            'display notification "Your {}-minute timer is done!" '
            'with title "Timer Complete" sound name "Glass"'.format(minutes),
        ])

    t = threading.Thread(target=_timer, daemon=True)
    t.start()

    # Also show an immediate confirmation notification
    subprocess.Popen([
        "osascript", "-e",
        'display notification "Timer ends at {}" '
        'with title "Timer Started — {} min"'.format(ends_at, minutes),
    ])

    return {"status": "running", "duration": "{} min".format(minutes),
            "ends_at": ends_at,
            "summary": "Timer started — {} min (ends {})".format(minutes, ends_at)}


# =====================================================================
# Alarm — macOS notification scheduled
# =====================================================================
def set_alarm(hour, minute):
    now = _time.localtime()
    alarm_secs = hour * 3600 + minute * 60
    now_secs = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec
    delta = alarm_secs - now_secs
    if delta <= 0:
        delta += 86400  # next day

    period = "AM" if hour < 12 else "PM"
    display_hour = hour if hour <= 12 else hour - 12
    if display_hour == 0:
        display_hour = 12
    time_str = "{}:{:02d} {}".format(display_hour, minute, period)

    def _alarm():
        _time.sleep(delta)
        subprocess.run([
            "osascript", "-e",
            'display notification "Alarm!" '
            'with title "Alarm — {}" sound name "Alarm"'.format(time_str),
        ])

    t = threading.Thread(target=_alarm, daemon=True)
    t.start()

    subprocess.Popen([
        "osascript", "-e",
        'display notification "Alarm scheduled" '
        'with title "Alarm set for {}"'.format(time_str),
    ])

    return {"status": "set", "time": time_str,
            "summary": "Alarm set for {}".format(time_str)}


# =====================================================================
# Reminder — adds to Apple Reminders app
# =====================================================================
def create_reminder(title, time="later"):
    try:
        script = (
            'tell application "Reminders"\n'
            '  tell list "Reminders"\n'
            '    make new reminder with properties '
            '{{name:"{} at {}"}}\n'
            '  end tell\n'
            'end tell'
        ).format(title.replace('"', '\\"'), time.replace('"', '\\"'))
        subprocess.run(["osascript", "-e", script], timeout=5,
                       capture_output=True, text=True)

        subprocess.Popen([
            "osascript", "-e",
            'display notification "{} at {}" '
            'with title "Reminder Created"'.format(
                title.replace('"', '\\"'), time.replace('"', '\\"')),
        ])

        return {"status": "created", "title": title, "time": time,
                "summary": "Reminder added: {} at {}".format(title, time)}
    except Exception as e:
        return {"error": str(e),
                "summary": "Could not create reminder"}


# =====================================================================
# Send Message — macOS notification (simulates delivery)
# =====================================================================
def send_message(recipient, message):
    try:
        subprocess.run([
            "osascript", "-e",
            'display notification "{}" '
            'with title "Message to {}" sound name "Tink"'.format(
                message.replace('"', '\\"'),
                recipient.replace('"', '\\"')),
        ], timeout=5)
        return {"status": "delivered", "to": recipient, "message": message,
                "timestamp": _time.strftime("%I:%M %p"),
                "summary": "Message sent to {} — \"{}\"".format(recipient, message)}
    except Exception as e:
        return {"error": str(e),
                "summary": "Could not send message"}


# =====================================================================
# Search Contacts — queries Apple Contacts
# =====================================================================
def search_contacts(query):
    try:
        script = (
            'tell application "Contacts"\n'
            '  set matchedPeople to every person whose name contains "{}"\n'
            '  set output to {{}}\n'
            '  repeat with p in matchedPeople\n'
            '    set end of output to name of p\n'
            '  end repeat\n'
            '  return output\n'
            'end tell'
        ).format(query.replace('"', '\\"'))
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=5,
        )
        raw = result.stdout.strip()
        if raw:
            names = [n.strip() for n in raw.split(",") if n.strip()]
            if names:
                return {"status": "found", "query": query,
                        "results": names[:5],
                        "summary": "Found: {}".format(", ".join(names[:3]))}
        return {"status": "not_found", "query": query,
                "summary": "No contacts found for '{}'".format(query)}
    except Exception as e:
        return {"error": str(e),
                "summary": "Could not search contacts"}
