from tools import simulated

ACTION_TOOLS = [
    {
        "name": "get_weather",
        "description": "Get current weather for a location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City name"}
            },
            "required": ["location"],
        },
    },
    {
        "name": "send_message",
        "description": "Send a message to a contact",
        "parameters": {
            "type": "object",
            "properties": {
                "recipient": {"type": "string", "description": "Name of the person to send the message to"},
                "message": {"type": "string", "description": "The message content to send"},
            },
            "required": ["recipient", "message"],
        },
    },
    {
        "name": "set_alarm",
        "description": "Set an alarm for a given time",
        "parameters": {
            "type": "object",
            "properties": {
                "hour": {"type": "integer", "description": "Hour to set the alarm for"},
                "minute": {"type": "integer", "description": "Minute to set the alarm for"},
            },
            "required": ["hour", "minute"],
        },
    },
    {
        "name": "set_timer",
        "description": "Set a countdown timer",
        "parameters": {
            "type": "object",
            "properties": {
                "minutes": {"type": "integer", "description": "Number of minutes"},
            },
            "required": ["minutes"],
        },
    },
    {
        "name": "play_music",
        "description": "Play a song or playlist",
        "parameters": {
            "type": "object",
            "properties": {
                "song": {"type": "string", "description": "Song or playlist name"},
            },
            "required": ["song"],
        },
    },
    {
        "name": "create_reminder",
        "description": "Create a reminder with a title and time",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Reminder title"},
                "time": {"type": "string", "description": "Time for the reminder (e.g. 3:00 PM)"},
            },
            "required": ["title", "time"],
        },
    },
    {
        "name": "search_contacts",
        "description": "Search for a contact by name",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name to search for"},
            },
            "required": ["query"],
        },
    },
]

_DISPATCH = {
    "get_weather": simulated.get_weather,
    "send_message": simulated.send_message,
    "set_alarm": simulated.set_alarm,
    "set_timer": simulated.set_timer,
    "play_music": simulated.play_music,
    "create_reminder": simulated.create_reminder,
    "search_contacts": simulated.search_contacts,
}


def execute_tool(name, args):
    fn = _DISPATCH.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    return fn(**args)
