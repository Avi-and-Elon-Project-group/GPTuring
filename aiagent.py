from flask_socketio import SocketIO, join_room, leave_room, send
import random
import time
import os
from openai import OpenAI
import prompts as p
import re


client = OpenAI()
delay = 2

bot_gender = "female"
bot_name = ""


def generate_prompt(human_name, bot_name, bot_gender, chat, user_message):
    chat_extender = []
    print("this is the chat", chat)
    print("this is the user message", user_message)
    context = [{'role': 'system', 'content': p.empty_prompt(human_name, bot_name, bot_gender)}]
    if chat != None:
        for message in chat:
            if 'sender' in message and message['sender'] != 'AI Agent':
                chat_extender.append({'role': 'user', 'content': "{user}: " + message.get('message')})
            else:
                chat_extender.append({'role': 'assistant', 'content': f"{{{bot_name}}}:" + message.get('message')})

    # context.extend(chat_extender)
    context = context + chat_extender
    context.append({'role': 'user', 'content': "{user}: " + f"{user_message}" + "\n" + f"{{{bot_name}}}:"})
    # print("this is the context", context)
    return context


def init_bot():
    """
    Set up the initial context for the conversation.

    :return: None
    """
    global context
    global bot_gender
    global bot_name
    # ToDo: here I can enter randomize of the bot name and gender
    bot_gender = random.choice(["man", "woman"])

    my_dir = os.path.dirname(__file__)
    file_path = os.path.join(my_dir, 'static/man_names.txt')
    if bot_gender == "man":
        file_path = os.path.join(my_dir, 'static/man_names.txt')
    else:
        file_path = os.path.join(my_dir, 'static/woman_names.txt')

    names_list = open(file_path, "r").readlines()

    bot_name = random.choice(names_list)
    print("chosen name is", bot_name, " and its gender", bot_gender)

    return {"bot_name": bot_name, "bot_gender": bot_gender}


def get_completion_from_messages(messages, model="gpt-3.5-turbo", temperature=0.7):
    """
    Get a chat completion from a list of messages using the OpenAI GPT-3.5-turbo model.

    :param list messages: List of messages in the conversation.
    :param str model: The OpenAI model to use (default is "gpt-3.5-turbo").
    :type model: str
    :param float temperature: Degree of randomness in the model's output (default is 0.7).
    :type temperature: float
    :return: The generated response from the model.
    :rtype: str
    """
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        max_tokens=200,
        temperature=temperature,
        stream=False, )
    
    response = remove_bracketed_text(response.choices[0].message.content)

    return response



def send_bot_message(prompt):
    """
    Simulate sending a message to the AI agent and receiving a response.

    :param list prompt: this is the prompt that the user has sent including the previous messages and system message
    :return: A dictionary containing the sender and the AI agent's response.
    :rtype: dict
    """
    response = get_completion_from_messages(prompt, model="gpt-3.5-turbo", temperature=0.7)
    words_count = response.count(' ')
    chars_count = len(response)
    # time.sleep(words_count / 2.0)  # **(1/2))*random.randrange(delay)
    # Calculate the time to sleep based on the number of characters in the response and the number of words
    time.sleep(2 * chars_count / words_count)
    return {
        "sender": "AI Agent",
        "message": response
    }


def get_bot_name():
    return bot_name

def remove_bracketed_text(text):
    # Regular expression to match {any-text}:
    pattern = r'\{[^}]*\}:'
    # Substitute the matched pattern with an empty string
    cleaned_text = re.sub(pattern, '', text)
    return cleaned_text
