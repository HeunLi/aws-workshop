import random
import string

def generate_code(prefix: str, string_length: int) -> str:
    letters = string.ascii_uppercase
    return prefix + ''.join(random.choice(letters) for _ in range(string_length))
