import socket
import threading
import pygame
import random
import sys

# 1. Player Username Setup
username = sys.argv[1] if len(sys.argv) > 1 else f"Player_{random.randint(100, 999)}"

# ========================================================
# NETWORK SETUP (TCP Client)
# ========================================================
# internet + tcp -- connection oriented
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# client -- bind? no, not necessary
try:
    # connect to server (IP + port)
    s.connect(("127.0.0.1", 6666))
    msg = f"NAME:{username}\n"
    s.send(str.encode(msg))
except Exception as e:
    print(f"Error connecting: {e}")
    sys.exit(1)

# ========================================================
# GRAPHICAL USER INTERFACE (Pygame Setup)
# ========================================================
pygame.init()
WIDTH, HEIGHT = 960, 560
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption(f"TCP Draw & Guess - {username}")
clock = pygame.time.Clock()

font = pygame.font.SysFont("Arial", 13)
font_bold = pygame.font.SysFont("Arial", 13, bold=True)
font_title = pygame.font.SysFont("Arial", 15, bold=True)
font_big = pygame.font.SysFont("Arial", 22, bold=True)

# State Variables
is_host = False
game_started = False
my_role = "LOBBY"  # "LOBBY", "DRAWER", "GUESSER"
host_name = ""
lobby_players = []
secret_word = ""
drawer_name = ""
hint_text = ""
status_text = "Connecting to lobby..."

# UI Rectangles
BANNER_RECT = pygame.Rect(12, 12, 570, 38)
CANVAS_RECT = pygame.Rect(12, 58, 570, 435)
canvas = pygame.Surface((CANVAS_RECT.width, CANVAS_RECT.height))
canvas.fill((255, 255, 255))

# 12 Colors + Eraser
COLORS = {
    "black": (20, 20, 20),
    "grey": (130, 130, 130),
    "white": (255, 255, 255),  # Eraser
    "red": (225, 40, 40),
    "orange": (245, 130, 30),
    "yellow": (245, 215, 20),
    "green": (35, 175, 60),
    "cyan": (30, 190, 220),
    "blue": (40, 90, 225),
    "purple": (145, 50, 200),
    "pink": (240, 110, 175),
    "brown": (125, 75, 40),
}
current_color_name = "black"
current_color = COLORS[current_color_name]

# Palette Buttons
color_buttons = []
btn_x = 14
btn_y = 505
for name, rgb in COLORS.items():
    color_buttons.append((pygame.Rect(btn_x, btn_y, 32, 30), name, rgb))
    btn_x += 37

clear_button_rect = pygame.Rect(495, 505, 85, 30)
start_button_rect = pygame.Rect(14, 505, 170, 32)

# Right: Chat & Guess Box
CHAT_RECT = pygame.Rect(595, 12, 350, 481)
INPUT_RECT = pygame.Rect(595, 505, 350, 32)

chat_messages = ["[Server] Connected to room lobby."]
input_text = ""
draw_lock = threading.Lock()

# Helper: Wrap chat messages so they fit inside the box
def wrap_text(text, font_obj, max_width):
    words = text.split(" ")
    lines = []
    curr = ""
    for w in words:
        test = f"{curr} {w}".strip()
        if font_obj.size(test)[0] <= max_width:
            curr = test
        else:
            if curr:
                lines.append(curr)
            curr = w
    if curr:
        lines.append(curr)
    return lines

# ========================================================
# NETWORK RECEIVER THREAD (TCP Concurrent Stream)
# ========================================================
def network_receiver():
    global is_host, game_started, my_role, host_name, lobby_players
    global secret_word, drawer_name, hint_text, status_text

    stream = ""
    while True:
        try:
            # recv -> read bytes from server stream
            buff = s.recv(1024)
            if not buff:
                break
            stream += buff.decode()

            # Message framing with '\n'
            while "\n" in stream:
                line, stream = stream.split("\n", 1)

                if line.startswith("HOST:"):
                    is_host = (line.split(":")[1] == "1")

                elif line.startswith("LOBBY:"):
                    parts = line.split(":", 2)
                    host_name = parts[1]
                    raw_list = parts[2].split(",") if len(parts) > 2 and parts[2] else []
                    lobby_players = raw_list
                    game_started = False
                    my_role = "LOBBY"

                    if is_host:
                        status_text = "[LOBBY] You are Host! Click 'Start Game' when ready."
                    else:
                        status_text = f"[LOBBY] Waiting for Host ({host_name}) to start..."

                elif line.startswith("ROLE:DRAWER:"):
                    game_started = True
                    my_role = "DRAWER"
                    secret_word = line.split(":", 2)[2].upper()
                    status_text = f"[YOUR TURN TO DRAW] Secret Word: {secret_word}"

                elif line.startswith("ROLE:GUESSER:"):
                    game_started = True
                    parts = line.split(":", 3)
                    my_role = "GUESSER"
                    drawer_name = parts[2]
                    hint_text = parts[3]
                    status_text = f"[{drawer_name} IS DRAWING] Word: {hint_text}"

                elif line.startswith("ROLE:WAIT"):
                    game_started = False
                    my_role = "LOBBY"
                    status_text = "Waiting for players to connect..."

                elif line.startswith("DRAW:"):
                    parts = line.split(":")
                    if len(parts) == 6:
                        _, x1, y1, x2, y2, col_name = parts
                        col = COLORS.get(col_name, (0, 0, 0))
                        brush = 10 if col_name == "white" else 3
                        with draw_lock:
                            pygame.draw.line(canvas, col, (int(x1), int(y1)), (int(x2), int(y2)), brush)

                elif line == "CLEAR":
                    with draw_lock:
                        canvas.fill((255, 255, 255))

                elif line.startswith("CHAT:"):
                    chat_messages.append(line[5:])
                    if len(chat_messages) > 30:
                        chat_messages.pop(0)

        except Exception:
            break

threading.Thread(target=network_receiver, daemon=True).start()

# ========================================================
# MAIN EVENT & RENDER LOOP
# ========================================================
last_pos = None
is_drawing = False
running = True

while running:
    clock.tick(60)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = event.pos

            # Lobby: Host clicks "Start Game"
            if not game_started:
                if is_host and start_button_rect.collidepoint(mouse_pos):
                    if len(lobby_players) >= 2:
                        s.send(str.encode("START_GAME\n"))
                    else:
                        chat_messages.append("[Server] You need at least 2 players to start!")

            # In Game: Drawer clicks Canvas or Palette
            else:
                if CANVAS_RECT.collidepoint(mouse_pos) and my_role == "DRAWER":
                    is_drawing = True
                    last_pos = (mouse_pos[0] - CANVAS_RECT.x, mouse_pos[1] - CANVAS_RECT.y)

                if my_role == "DRAWER":
                    for rect, name, _ in color_buttons:
                        if rect.collidepoint(mouse_pos):
                            current_color_name = name
                            current_color = COLORS[name]

                    if clear_button_rect.collidepoint(mouse_pos):
                        with draw_lock:
                            canvas.fill((255, 255, 255))
                        s.send(str.encode("CLEAR\n"))

        elif event.type == pygame.MOUSEBUTTONUP:
            is_drawing = False
            last_pos = None

        elif event.type == pygame.MOUSEMOTION and is_drawing and my_role == "DRAWER" and game_started:
            mouse_pos = event.pos
            if CANVAS_RECT.collidepoint(mouse_pos):
                cur_pos = (mouse_pos[0] - CANVAS_RECT.x, mouse_pos[1] - CANVAS_RECT.y)
                if last_pos:
                    brush = 10 if current_color_name == "white" else 3
                    with draw_lock:
                        pygame.draw.line(canvas, current_color, last_pos, cur_pos, brush)
                    msg = f"DRAW:{last_pos[0]}:{last_pos[1]}:{cur_pos[0]}:{cur_pos[1]}:{current_color_name}\n"
                    # text encoded
                    s.send(str.encode(msg))
                last_pos = cur_pos

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_RETURN:
                if input_text.strip():
                    msg = f"GUESS:{input_text.strip()}\n"
                    # text encoded
                    s.send(str.encode(msg))
                    input_text = ""
            elif event.key == pygame.K_BACKSPACE:
                input_text = input_text[:-1]
            else:
                if len(input_text) < 40 and event.unicode.isprintable():
                    input_text += event.unicode

    # Render Screen
    screen.fill((236, 239, 244))

    # Top Banner
    if not game_started:
        banner_bg, banner_border = (255, 248, 220), (220, 160, 20)
    elif my_role == "DRAWER":
        banner_bg, banner_border = (220, 248, 230), (40, 160, 80)
    else:
        banner_bg, banner_border = (225, 238, 255), (60, 120, 210)

    pygame.draw.rect(screen, banner_bg, BANNER_RECT, border_radius=6)
    pygame.draw.rect(screen, banner_border, BANNER_RECT, 2, border_radius=6)
    banner_lbl = font_title.render(status_text, True, (20, 20, 20))
    screen.blit(banner_lbl, (BANNER_RECT.x + 12, BANNER_RECT.y + 8))

    # Canvas Area
    if not game_started:
        # Lobby Room Card
        pygame.draw.rect(screen, (255, 255, 255), CANVAS_RECT, border_radius=4)
        pygame.draw.rect(screen, (170, 175, 185), CANVAS_RECT, 2, border_radius=4)

        lobby_title = font_big.render("GAME LOBBY", True, (40, 60, 100))
        screen.blit(lobby_title, (CANVAS_RECT.x + 24, CANVAS_RECT.y + 24))

        info_sub = font_bold.render(f"Room Host: {host_name}  |  Connected Players: {len(lobby_players)}", True, (70, 70, 80))
        screen.blit(info_sub, (CANVAS_RECT.x + 24, CANVAS_RECT.y + 62))

        p_y = CANVAS_RECT.y + 100
        for i, p_info in enumerate(lobby_players, 1):
            is_me = (p_info.split()[0] == username)
            color = (30, 140, 50) if is_me else (40, 45, 55)
            tag = " (You)" if is_me else ""
            txt = font.render(f"{i}.  {p_info}{tag}", True, color)
            screen.blit(txt, (CANVAS_RECT.x + 36, p_y))
            p_y += 26

        if len(lobby_players) < 2:
            wait_msg = font_bold.render("Need at least 2 players to start the game...", True, (190, 40, 40))
            screen.blit(wait_msg, (CANVAS_RECT.x + 24, CANVAS_RECT.y + 380))
        else:
            ready_msg = font_bold.render("Ready! Host can click 'Start Game' below.", True, (35, 150, 55))
            screen.blit(ready_msg, (CANVAS_RECT.x + 24, CANVAS_RECT.y + 380))

        if is_host:
            can_start = (len(lobby_players) >= 2)
            btn_bg = (40, 180, 65) if can_start else (180, 185, 190)
            pygame.draw.rect(screen, btn_bg, start_button_rect, border_radius=5)
            btn_txt = font_bold.render("Start Game" if can_start else "Wait for Players", True, (255, 255, 255))
            screen.blit(btn_txt, (start_button_rect.x + 25, start_button_rect.y + 7))
        else:
            host_wait_lbl = font.render(f"Waiting for Host ({host_name}) to click Start...", True, (80, 85, 95))
            screen.blit(host_wait_lbl, (start_button_rect.x, start_button_rect.y + 7))

    else:
        # Active Drawing Canvas
        with draw_lock:
            screen.blit(canvas, (CANVAS_RECT.x, CANVAS_RECT.y))
        pygame.draw.rect(screen, (170, 175, 185), CANVAS_RECT, 2, border_radius=4)

        # 12 Colors
        for rect, name, col in color_buttons:
            btn_color = col if my_role == "DRAWER" else (200, 200, 200)
            pygame.draw.rect(screen, btn_color, rect, border_radius=4)
            border_col = (180, 180, 180) if name == "white" else (100, 100, 100)
            pygame.draw.rect(screen, border_col, rect, 1, border_radius=4)
            if name == current_color_name and my_role == "DRAWER":
                pygame.draw.rect(screen, (255, 215, 0), rect, 3, border_radius=4)

        # Clear Button
        clear_bg = (210, 215, 220) if my_role == "DRAWER" else (230, 230, 230)
        pygame.draw.rect(screen, clear_bg, clear_button_rect, border_radius=4)
        clear_lbl = font.render("Clear", True, (30, 30, 30) if my_role == "DRAWER" else (140, 140, 140))
        screen.blit(clear_lbl, (clear_button_rect.x + 26, clear_button_rect.y + 7))

    # Right: Chat Box
    pygame.draw.rect(screen, (255, 255, 255), CHAT_RECT, border_radius=6)
    pygame.draw.rect(screen, (180, 185, 195), CHAT_RECT, 2, border_radius=6)

    header = font_bold.render("Chat, Guesses & Scoreboard", True, (50, 55, 65))
    screen.blit(header, (CHAT_RECT.x + 12, CHAT_RECT.y + 10))

    wrapped_lines = []
    max_w = CHAT_RECT.width - 24
    for raw in reversed(chat_messages):
        col = (205, 30, 30) if "[Winner]" in raw else ((25, 130, 45) if "[Server]" in raw else ((190, 100, 0) if "[Scoreboard]" in raw else (30, 35, 45)))
        for sub in reversed(wrap_text(raw, font, max_w)):
            wrapped_lines.append((sub, col))
            if len(wrapped_lines) >= 20: break
        if len(wrapped_lines) >= 20: break

    y_offset = CHAT_RECT.y + 38
    for line_text, line_col in reversed(wrapped_lines):
        screen.blit(font.render(line_text, True, line_col), (CHAT_RECT.x + 12, y_offset))
        y_offset += 21

    # Input Field
    pygame.draw.rect(screen, (255, 255, 255), INPUT_RECT, border_radius=4)
    pygame.draw.rect(screen, (90, 135, 225), INPUT_RECT, 2, border_radius=4)

    if input_text:
        disp, col = input_text + "|", (20, 20, 20)
    else:
        if game_started and my_role == "DRAWER":
            disp, col = "(You are drawing - other players guess)", (130, 130, 130)
        else:
            disp, col = "Type guess or chat & press Enter...", (140, 145, 155)

    screen.blit(font.render(disp, True, col), (INPUT_RECT.x + 10, INPUT_RECT.y + 7))

    pygame.display.flip()

s.close()
pygame.quit()
