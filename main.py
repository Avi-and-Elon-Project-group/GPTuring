"""
Flask Chat Website

This Flask application implements a chat system with Testers and Feedback functionality using Flask-SocketIO.

Dependencies:
- Flask: Web framework for building the application.
- Flask-SocketIO: Extension for handling WebSocket communication.
- utils.py: Module containing utility functions, such as generate_room_code.
- aiagent.py: Module for interacting with the AI agent (send_bot_message).

How to Run:
1. Install dependencies using 'pip install flask flask-socketio'.
2. Run the application using 'python main.py'.

Routes and Functions:
- '/' (home): Renders the home page with options to create or join a chat room.
- '/room': Renders the chat room page where Testers can interact with the AI agent.
- '/info': Renders the information page.
- '/feedback': Renders the feedback page for Testers to provide feedback.

SocketIO Events:
- 'connect': Handles the connection of users to the chat room.
- 'message': Handles incoming messages in the chat room.
- 'disconnect': Handles user disconnection from the chat room.

Note: Customize the feedback.html page for your survey needs.

Authors: Avraham Rahimov, Elon Ezra
"""
from flask import Flask, request, render_template, redirect, url_for, session, Response, send_from_directory
from flask_socketio import SocketIO, join_room, leave_room, send
import os
import csv
import datetime
import time
from datetime import timedelta
import logging

from utils import generate_room_code
from aiagent import generate_prompt, send_bot_message, init_bot, get_bot_name

import random
import sys  # for trigger (or not) the code for IP blocking

app = Flask(__name__)
app.config["DEBUG"] = True if len(sys.argv) > 1 and  sys.argv[1] == "disable" else False
app.config["APPLICATION_ROOT"] = "/"
app.config["PREFERRED_URL_SCHEME"] = "https"

app.config['SECRET_KEY'] = 'SDKFJSDFOWEIOF'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=10)  # Set session to expire after 10 minutes

socketio = SocketIO(app, engineio_logger=True, logger=True)
tester_amount = 5
duration_of_session = 30 if len(sys.argv) > 1 and  sys.argv[1] == "disable" else 300 # configure how long the chat will run in seconds
# Initialize rooms
Testers_rooms = {}
Master_rooms = {}
Info_about_rooms = ""
# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')


def check_participant():
    """
    Checks if the client has participated in the experiment before.

    :return: True if the client is a new participant, False otherwise.
    """
    if request.headers.getlist("X-Forwarded-For"):
        client_ip = request.headers.getlist("X-Forwarded-For")[0]
    else:
        client_ip = request.remote_addr
    # Read existing participants
    participants = set()
    try:
        with open('participants.csv', 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                participants.add(row[0])
    except FileNotFoundError:
        pass

    # Check if the client has participated before
    if client_ip in participants:
        return False

    # If not, add the new participant
    with open('participants.csv', 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([client_ip])

    return True


@app.route('/', methods=["GET", "POST"])
def home():
    """
    Renders the home page, allowing users to create or join chat rooms.

    :return: Rendered template for the home page.
    :rtype: Flask.Response
    """
    session.clear()

    if request.method == "POST":

        name = request.form.get('name')
        request.form.get('create', False)
        code = request.form.get('code')
        join = request.form.get('join', False)

        if not name:
            return render_template('home.html', error="Name is required", code=code, rooms=Testers_rooms)

        if join != False:
            available_room = search_for_room()
            # there is no available room thus, the system must create a new room and set the user to be tester
            if available_room is None:
                room_code = generate_room_code(6, list(Testers_rooms.keys()))
                bot_room = room_code + "_b"
                human_room = room_code + "_h"
                session['role'] = "tester"

                # set data for bot only room
                Testers_rooms[bot_room] = {'members': 1, 'members_name': [], 'messages': []}
                Testers_rooms[bot_room]["server_messages"] = []
                session['room_b'] = bot_room
                bot_data = init_bot()
                session['bot_name'] = bot_data["bot_name"]
                session['bot_gender'] = bot_data["bot_gender"]
                session['name'] = name
                # set data for human only room
                Testers_rooms[human_room] = {'members': 0, 'members_name': [], 'messages': []}
                Testers_rooms[human_room]["last_member_was_connected"] = 0

                session['room_h'] = human_room
                # session['name'] = name
                return redirect(url_for('tester_window'))

            else:  # there is an available room so, the user automatically(by the system) join this room
                session['role'] = "experimenter"
                session['room'] = available_room
                session['name'] = name
                stop_overlay()
                return redirect(url_for('experimenter_window'))

    else:
        return render_template('home.html', rooms=Testers_rooms)


@socketio.on('stop overlay')
def stop_overlay():
    # Your code here
    socketio.emit('overlay stopped', "hide_dino")


def search_for_room():
    """
    Search for a chat room with two members (tester and bot) and return its key.

    :return: Room code with two members, or None if no such room is found.
    :rtype: str or None
    """
    for room_key in Testers_rooms.keys():
        # check the amount of users and check if the room is for humans
        # That means that i the room there are the tester and the bot thus, human can join(2 members)
        if Testers_rooms[room_key]["members"] == 1 and room_key[-1] == 'h':
            # currently)
            return room_key
    return None


@app.route('/room', methods=["GET", "POST"])
def room():
    """
    Renders the chat room page for communication.

    :return: Rendered template for the chat room page.
    :rtype: Flask.Response
    """
    if session.get('role') == "tester":
        q1 = request.args.get('room_code')
        room = q1
        session['room'] = room
        name = session.get('name')

        if name is None or room is None or room not in Testers_rooms:
            return redirect(url_for('home'))

        messages = Testers_rooms[room]['messages']
        return render_template('room.html', room=room, user=name, messages=messages)

    elif session.get('role') == "experimenter":
        room = session.get('room')
        name = session.get('name')
        if name is None or room is None or room not in Testers_rooms:
            return redirect(url_for('home'))
        messages = Testers_rooms[room]['messages']
        return render_template('room.html', room=room, user=name, messages=messages)


@socketio.on('connect')
def handle_connect():
    """
    Handles user connection to the chat room.

    :return: None
    """
    logging.debug(f"User connected")
    name = session.get('name')
    room = session.get('room')
    bot_name = session.get('bot_name')
    logging.debug(f"Session data - name: {name}, room: {room}, bot_name: {bot_name}")

    if name is None and room is None:
        return

    if room is None:
        logging.debug(f"Master {name} connected with room: {room}")
        Master_rooms[name] = {'room': name+'_m'}
        join_room(Master_rooms[name]['room'])
        logging.debug(f"{name} joined room {room} Master_rooms: {Master_rooms}")
        return
    
    if Testers_rooms[room]["members"] == 2:
        # Check if the client has participated before
        if len(sys.argv) > 1:
            if sys.argv[1] == "disable":
                pass
            else:
                if not check_participant():
                    return render_template('blocked.html')
        else:
            if not check_participant():
                return render_template('blocked.html')

    if room not in Testers_rooms:
        Testers_rooms[room] = {'members': 0, 'members_name': [], 'messages': []}  # Create the room if it doesn't exist
        logging.debug(f"Created new room: {room}")

    if name not in Testers_rooms[room]["members_name"]:
        Testers_rooms[room]["members_name"].append(name)
        Testers_rooms[room]["members"] += 1
        logging.debug(f"Added {name} to room {room}")

    join_room(room)
    logging.debug(f"{name} joined room {room}")

    if room[-1] == "h" and Testers_rooms[room]["members"] == 2 and Testers_rooms[room].get("last_member_was_connected") == 0:
        n1 = Testers_rooms[room]["members_name"][0]
        n2 = Testers_rooms[room]["members_name"][1]
        send({"sender": "","message": f"{n1} has entered the chat"}, to=room)
        send({"sender": "","message": f"{n2} has entered the chat" }, to=room)
        Testers_rooms[room]["last_member_was_connected"] += 1
        logging.debug(f"Both members connected in room {room}")


    if room[-1] == "b":
        send({"sender": "", "message": f"{name} has entered the chat" }, to=room)
        send({"sender": "","message": f"{bot_name} has entered the chat"}, to=room)
        logging.debug(f"{name} and {bot_name} entered the chat in room {room}")

    if Testers_rooms[room]["members"] == 2 and room[-1] == 'h':
        # Start a background task that will disconnect the users after 60 seconds
        socketio.start_background_task(disconnect_users, room, Testers_rooms[room]["members_name"])

@socketio.on('stop connection')
def disconnect_users(room, names):
    """
    Disconnects the users of a room and redirects them to the thank-you page.

    :param str room: The room code.
    :return: None
    """
    # Send a message to the users that the time is up
    print("Disconnecting users in room:", room)

    socketio.sleep(duration_of_session)
    # print("in disconnect room: ", room)
    if room in Testers_rooms:
        if (Testers_rooms[room].get("last_warning_for_disconnect") is None):
            # socketio.emit("message", {"sender": "", "message": "1 minute to finish the conversation."}, to=room)
            socketio.emit("message", { "sender": "","message": "1 minute to finish the conversation."}, to=[room, room[:-1] + "b"])
            Testers_rooms[room]["last_warning_for_disconnect"] = True
    else:
        return

    socketio.sleep(10)

    class MySocket:
        """
        A class to manage the stopping of the conversation, because it may happen
        that two or more sockets will try to do something at the same time, we want to
        avoid that with a response flag and while loop explained later on.
        """
        def __init__(self):
            self.response = 0

        def change_response(self):
            self.response += 1
            print("Response changed to 1")

    my_socket = MySocket()
    # Send a message by while loop to the users that the time is up with a callback to change the response flag
    # within the MySocket class.
    # while my_socket.response <= 1:
    logging.debug("stopping_conv emitted")
    logging.debug(f"room: {room}, names: {names}")
    rooms_to_emit = [room, room[:-1] + "b"]
    for name in names:
        master_room = Master_rooms.get(name, {}).get('room')
        if master_room:
            rooms_to_emit.append(master_room)
    socketio.emit("stopping_conv",to=rooms_to_emit ,callback = my_socket.change_response)
    print("stopping_conv emitted")
    socketio.sleep(3)

    # trigger the code
    # experimenter_finished()


def generate_unique_code():
    return str(random.randint(100000, 999999))


@app.route('/end_chat/<role>', methods=["GET", "POST"])
def end_chat(role):
    # print("\n in end chat\n")
    # Generate and store the unique code in the session
    logging.debug(f"end_chat called with role: {role}")

    room_code = request.args.get('room_code')
    logging.debug(f"Room code: {room_code}")

    if role == 'experimenter':
        session['unique_code'] = generate_unique_code()
        logging.debug(f"Generated unique code for experimenter: {session['unique_code']}")


        with open('code_reward.csv', '+a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([session['unique_code']])
        return redirect(url_for('thank_you'))
    elif role == 'tester':
        session['unique_code'] = generate_unique_code()

        with open('code_reward.csv', '+a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([session['unique_code']])

        data_to_pass = {'room_code': room_code}
        session['data_to_pass'] = data_to_pass
        return redirect(url_for('feedback'))
        # return render_template('feedback.html', room_code=room_code)
    else:
        return 'Invalid role', 400


@socketio.on('experimenter_finished')
def experimenter_finished():
    """
    Emits a message to trigger the 6-digit code for the experimenters.

    :return: None
    """
    socketio.emit('experimenter_finished')


@socketio.on('message')
def handle_message(payload):
    """
    Handles user messages, including AI agent responses.

    :param dict payload: Message payload containing the user's message.
    :return: None
    """
    # logging.debug(f"handle_message called with payload: {payload}")
    room = session.get('room')
    name = session.get('name')
    bot_name = session.get('bot_name')
    bot_gender = session.get('bot_gender')

    if room not in Testers_rooms:
        return

    user_message = payload["message"]

    message2 = {
        "sender": name,
        "message": payload["message"]
    }
    send(message2, to=room)

    # logging.debug(f"Sent message to room {room}: {message2}")

    Testers_rooms[room]["messages"].append(message2)
    with open('conversations.csv', 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        message = Testers_rooms[room]["messages"][-1]
        if room[-1] == "h":
            writer.writerow(
                [datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), room, name + ' (user)', message["message"]])
        else:
            writer.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), room,
                             'bot' if message['sender'] == bot_name else 'user', message["message"]])

    if room[-1] == "b":
        prompt = generate_prompt(name, bot_name, bot_gender, Testers_rooms[room]["messages"], user_message)
        # print("prompt: ", prompt)
        ai_response = send_bot_message(prompt)

        message1 = {
            "sender": "AI Agent",
            "message": ai_response["message"]
        }
        send(message1, to=room)

        if Testers_rooms.get(room) is not None:
            Testers_rooms[room]["messages"].append(message1)

            with open('conversations.csv', 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                message = Testers_rooms[room]["messages"][-1]
                writer.writerow([datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), room,
                                 'bot' if message['sender'] == 'AI Agent' else 'user (tester)', message["message"]])


@socketio.on('disconnect')
def handle_disconnect():
    """
    Handles user disconnection from the chat room.

    :return: None
    """
    room = session.get("room")
    name = session.get("name")

    leave_room(room)

    if room in Testers_rooms:
        if (room[-1] == 'b'):
            Testers_rooms[room]["members"] -= 1
        Testers_rooms[room]["members"] -= 1
        if Testers_rooms[room]["members"] <= 0:
            del Testers_rooms[room]
        if name in Master_rooms:
            del Master_rooms[name]
        logging.debug(f"Masters: {Master_rooms}")

    send({"message": f"{name} has left the chat", "sender": ""}, to=room)
    # socketio.emit('force_disconnect', {}, to=room)


@app.route('/feedback')
def feedback():
    """
    Renders the feedback page.

    :return: Rendered template for the feedback page.
    :rtype: Flask.Response
    """
    # print("In feedback")
    data_passed = session.get('data_to_pass', {})
    # print("Data passed:", data_passed)
    return render_template('feedback.html', room_code=data_passed.get('room_code', 'Error: Room code not found'))


@app.route('/thank_you', methods=['POST'])
def submit_feedback():
    """
    Handles the submission of feedback data from Testers.

    :return: Rendered template for the thank-you page.
    :rtype: Flask.Response
    """
    info_about_rooms_list = Info_about_rooms.split(" ")
    real_identity_a = info_about_rooms_list[info_about_rooms_list.index("A=") + 1]
    real_identity_b = info_about_rooms_list[info_about_rooms_list.index("B=") + 1]
    identity_a = request.form.get('identityA')
    identity_b = request.form.get('identityB')
    room_code = request.form.get('room_code')
    human_feedback_data_a = []
    bot_feedback_data_a = []
    human_feedback_data_b = []
    bot_feedback_data_b = []

    if identity_a == 'human':
        human_feedback_data_a = [
            request.form.get('human_reasonA', ''),
            request.form.get('human_momentA', ''),
            request.form.get('human_ratingA', ''),
            real_identity_a,
            identity_a
        ]
    elif identity_a == 'bot':
        bot_feedback_data_a = [
            request.form.get('bot_reasonA', ''),
            request.form.get('bot_momentA', ''),
            request.form.get('bot_ratingA', ''),
            request.form.get('bot_improvementA', ''),
            real_identity_a,
            identity_a
        ]

    if identity_b == 'human':
        human_feedback_data_b = [
            request.form.get('human_reasonB', ''),
            request.form.get('human_momentB', ''),
            request.form.get('human_ratingB', ''),
            real_identity_b,
            identity_b
        ]
    elif identity_b == 'bot':
        bot_feedback_data_b = [
            request.form.get('bot_reasonB', ''),
            request.form.get('bot_momentB', ''),
            request.form.get('bot_ratingB', ''),
            request.form.get('bot_improvementB', ''),
            real_identity_b,
            identity_b
        ]

    # Demographic information
    age = request.form.get('age', '')
    gender = request.form.get('gender', '')
    education = request.form.get('education', '')
    ai_interaction = request.form.get('ai_interaction', '')
    language = request.form.get('language', '')
    country = request.form.get('country', '')
    turing_test = request.form.get('turing_test', '')

    human_feedback_data = human_feedback_data_a or human_feedback_data_b
    bot_feedback_data = bot_feedback_data_a or bot_feedback_data_b
    room_code = [room_code]

    demographic_data = [
        age,
        gender,
        education,
        ai_interaction,
        language,
        country,
        turing_test
    ]

    # Logic to write data to CSV
    file_path = 'Bot_Human_Feedback.csv'
    file_exists = os.path.exists(file_path)
    header = ['Room Code', 'human reason', 'human specific cause', 'human rating', 'real identity 1', 'Tester guess 1',
              'bot reason', 'bot moment', 'bot rating', 'bot improvement', 'real identity 2', 'Tester guess 2',
              'Age', 'Gender', 'Education', 'AI Interaction', 'Language',
              'Country', 'Turing Test']

    with open(file_path, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(header)
        writer.writerow(room_code + human_feedback_data + bot_feedback_data + demographic_data)

    # Redirect the user or render a "thank you" page
    return render_template('thank_you.html', code=session.get('unique_code', 'Error: Code not found'))


@app.route('/tester_window', methods=["GET", "POST"])
def tester_window():
    """
    Renders the tester_window page with the room codes and randomized titles for each room i.e.
    the titles are "Candidate A" or "Candidate B".
    :return: Flask.Response
    """
    global Info_about_rooms
    # room_a = random.choice(['A', 'B'])
    # room_b = 'B' if room_a == 'A' else 'A'
    # title_a = f'Candidate {room_a}'
    # title_b = f'Candidate {room_b}'
    room1 = session.get("room_b")
    room2 = session.get("room_h")
    room_codes = [room1, room2]
    random.shuffle(room_codes)
    if room_codes[1] is not None:
        if room_codes[1][-1] == 'b':
            Info_about_rooms += " Candidate A= bot Candidate B= human "
        else:
            Info_about_rooms += " Candidate A= human Candidate B= bot "
    else:
        return redirect(url_for('home'))

    return render_template('tester_window.html', room_code1=room_codes[1], room_code2=room_codes[0])


@app.route('/experimenter_window', methods=["GET", "POST"])
def experimenter_window():
    return render_template('experimenter_window.html')


@app.route('/dino_game')
def dino_game():
    return render_template('dino_game.html')


@app.route('/managing_window')
def managing_window():
    return render_template('managing_window.html', varible=Testers_rooms)


@app.route('/thank_you')
def thank_you():
    # Retrieve the unique code from the session
    unique_code = session.get('unique_code', 'Error: Code not found')
    return render_template('thank_you.html', code=unique_code)


@app.route('/get-file/<filename>')
def get_file(filename):
    return send_from_directory(directory='static', filename=filename)


if __name__ == '__main__':
    # app.run(threaded=True)
    d = False
    if len(sys.argv) > 1 and sys.argv[1] == "disable":
        d  = True
    socketio.run(app, debug = d , allow_unsafe_werkzeug=True)
    # socketio.run(app, debug=True, allow_unsafe_werkzeug=True, host='localhost', port=5000)
