

import sys

# http://www.pixelbeat.org/programming/stdio_buffering/
BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(30, 38)
LIGHTBLACK, LIGHTRED, LIGHTGREEN, LIGHTYELLOW, LIGHTBLUE, LIGHTMAGENTA, LIGHTCYAN, LIGHTWHITE = range(90, 98)

# These are the escape sequences need to get colored ouput
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[%dm"
BOLD_SEQ = "\033[1m"

def print_colored(message, color=BLACK, bold=False):
    if bold:
        sys.stdout.write(COLOR_SEQ % (color) + BOLD_SEQ)
    else:
        sys.stdout.write(COLOR_SEQ % (color))
    sys.stdout.write(message)
    sys.stdout.write(RESET_SEQ)
