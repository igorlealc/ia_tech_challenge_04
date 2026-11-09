def log_error(msg: str):
    print(f"\033[31m{msg}!\033[0m")

def log_error(e: Exception):
    print(str(e))

def log_info(msg: str):
    print(f"\033[34m{msg}!\033[0m")