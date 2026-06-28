def evaluate_event_response(event, player_response):

    length = len(player_response)

    if length < 30:
        score = 3
        feedback = "Your decree was too vague to inspire confidence."
    elif length < 120:
        score = 6
        feedback = "Your decree showed some leadership, but lacked detail."
    else:
        score = 8
        feedback = "Your decree was thoughtful, practical, and reassuring."

    return {
        "empathy": score,
        "practicality": score,
        "leadership": score,
        "feedback": feedback,
    }


