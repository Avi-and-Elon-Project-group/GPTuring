from string import ascii_letters
import random


def generate_room_code(length: int, existing_codes: list) -> str:
    """
    Generate a unique room code of a specified length.

    :param int length: The length of the room code.
    :param list existing_codes: List of existing room codes to avoid duplication.
    :return: A unique room code.
    :rtype: str
    """
    while True:
        code_chars = [random.choice(ascii_letters) for _ in range(length)]
        code = ''.join(code_chars)

        if code not in existing_codes:
            return code
