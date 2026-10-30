import socket
import pygame
import json
import random
import sys

# 1. Player Setup
player_name = sys.argv[1] if len(sys.argv) > 1 else f"P_{random.randint(100, 999)}"
my_color = (random.randint(50, 230), random.randint(50, 230), random.randint(50, 230))

# ========================================================
# NETWORK SETUP (UDP Client)
# ========================================================
# internet + udp -- open internet
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# text + touple (IP + port)
SERVER_ADDR = ("127.0.0.1", 5555)
# client -- bind? no, not necessary
s.setblocking(False)

# ========================================================
# GRAPHICAL USER INTERFACE (Pygame Setup)
# ========================================================
pygame.init()
WIDTH, HEIGHT = 900, 650
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption(f"Agar.io UDP Client - {player_name}")
clock = pygame.time.Clock()

font = pygame.font.SysFont("Arial", 13)
font_bold = pygame.font.SysFont("Arial", 13, bold=True)
font_title = pygame.font.SysFont("Arial", 15, bold=True)
font_victory = pygame.font.SysFont("Arial", 24, bold=True)

players = {}
food = []
winner = ""
WIN_RADIUS = 75.0

running = True
while running:
    clock.tick(60)

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    # Send current mouse target: "MOVE:id:x:y:r:g:b"
    mx, my = pygame.mouse.get_pos()
    msg = f"MOVE:{player_name}:{mx}:{my}:{my_color[0]}:{my_color[1]}:{my_color[2]}"
    # text + touple (IP + port)
    s.sendto(str.encode(msg), SERVER_ADDR)

    # Receive world snapshot via UDP
    try:
        # recvfrom -> 2 variables, message + address
        buff, addr = s.recvfrom(8192)
        world = json.loads(buff.decode())
        players = world.get("players", {})
        food = world.get("food", [])
        winner = world.get("winner", "")
    except BlockingIOError:
        pass

    # Render Arena Scene
    screen.fill((242, 245, 248))

    # Grid background
    for gx in range(0, WIDTH, 50):
        pygame.draw.line(screen, (230, 233, 238), (gx, 0), (gx, HEIGHT))
    for gy in range(0, HEIGHT, 50):
        pygame.draw.line(screen, (230, 233, 238), (0, gy), (WIDTH, gy))

    # Draw Colorful Food Pellets
    for f in food:
        fx, fy = int(f["x"]), int(f["y"])
        fc = tuple(f.get("c", [40, 180, 50]))
        pygame.draw.circle(screen, fc, (fx, fy), 4)

    # Draw All Connected Players & Bots
    my_current_radius = 20.0
    for pid, pdata in players.items():
        px, py = int(pdata["x"]), int(pdata["y"])
        pr = int(pdata["r"])
        pcolor = tuple(pdata.get("color", [200, 50, 50]))
        is_immune = pdata.get("immune", 0) == 1

        if pid == player_name:
            my_current_radius = pr

        # Draw Spawn Protection Shield if immune
        if is_immune:
            pygame.draw.circle(screen, (40, 200, 240), (px, py), pr + 6, 3)

        # Draw player blob
        pygame.draw.circle(screen, pcolor, (px, py), pr)

        # Draw Outline
        border_col = (20, 20, 20) if pid == player_name else (90, 90, 90)
        border_w = 3 if pid == player_name else 1
        pygame.draw.circle(screen, border_col, (px, py), pr, border_w)

        # Render ONLY the name on the field
        label = font_bold.render(pid, True, (20, 20, 20))
        screen.blit(label, (px - label.get_width() // 2, py - pr - 18))

    # ====================================================
    # SIZE PROGRESS BAR TO WIN (Bottom Center)
    # ====================================================
    bar_w, bar_h = 280, 18
    bar_x = (WIDTH - bar_w) // 2
    bar_y = HEIGHT - 35

    # Percentage to max size (from initial 20 to WIN_RADIUS 75)
    progress = max(0.0, min(1.0, (my_current_radius - 20.0) / (WIN_RADIUS - 20.0)))

    pygame.draw.rect(screen, (255, 255, 255), (bar_x - 2, bar_y - 2, bar_w + 4, bar_h + 4), border_radius=5)
    pygame.draw.rect(screen, (215, 220, 228), (bar_x, bar_y, bar_w, bar_h), border_radius=4)
    # Fill progress
    fill_w = int(bar_w * progress)
    if fill_w > 0:
        fill_col = (245, 175, 35) if progress > 0.8 else (50, 180, 80)
        pygame.draw.rect(screen, fill_col, (bar_x, bar_y, fill_w, bar_h), border_radius=4)

    bar_label = font_bold.render(f"Size Progress: {int(progress * 100)}% (Goal: Full Size)", True, (40, 45, 55))
    screen.blit(bar_label, (bar_x + (bar_w - bar_label.get_width()) // 2, bar_y - 20))

    # ====================================================
    # SIDE RANKING / LEADERBOARD (UDP Authoritative State)
    # ====================================================
    board_w, board_h = 190, 210
    board_rect = pygame.Rect(WIDTH - board_w - 15, 15, board_w, board_h)

    board_surf = pygame.Surface((board_w, board_h), pygame.SRCALPHA)
    board_surf.fill((20, 25, 35, 210))
    screen.blit(board_surf, (board_rect.x, board_rect.y))
    pygame.draw.rect(screen, (60, 70, 90), board_rect, 2, border_radius=6)

    title = font_title.render("LEADERBOARD", True, (245, 195, 40))
    screen.blit(title, (board_rect.x + 14, board_rect.y + 10))
    pygame.draw.line(screen, (80, 90, 110), (board_rect.x + 10, board_rect.y + 32),
                     (board_rect.x + board_w - 10, board_rect.y + 32))

    sorted_players = sorted(players.items(), key=lambda item: item[1].get("score", 0), reverse=True)

    row_y = board_rect.y + 40
    for rank, (pid, pdata) in enumerate(sorted_players[:7], 1):
        is_me = (pid == player_name)
        text_color = (100, 230, 140) if is_me else (230, 235, 245)
        tag = " *" if is_me else ""

        rank_txt = font_bold.render(f"{rank}. {pid}{tag}", True, text_color)
        score_txt = font.render(f"{pdata.get('score', 0)} pts", True, text_color)

        screen.blit(rank_txt, (board_rect.x + 14, row_y))
        screen.blit(score_txt, (board_rect.x + board_w - score_txt.get_width() - 14, row_y))
        row_y += 23

    # ====================================================
    # VICTORY OVERLAY (When a player reaches full size)
    # ====================================================
    if winner:
        overlay_w, overlay_h = 480, 140
        overlay_x = (WIDTH - overlay_w) // 2
        overlay_y = (HEIGHT - overlay_h) // 2

        vic_surf = pygame.Surface((overlay_w, overlay_h), pygame.SRCALPHA)
        vic_surf.fill((15, 20, 30, 235))
        screen.blit(vic_surf, (overlay_x, overlay_y))
        pygame.draw.rect(screen, (245, 195, 40), (overlay_x, overlay_y, overlay_w, overlay_h), 3, border_radius=8)

        if winner == player_name:
            main_msg = font_victory.render("VICTORY! YOU REACHED FULL SIZE!", True, (255, 215, 0))
            sub_msg = font_bold.render("You reached maximum size and won the match!", True, (100, 240, 140))
        else:
            main_msg = font_victory.render(f"{winner} REACHED FULL SIZE!", True, (255, 215, 0))
            sub_msg = font_bold.render(f"{winner} reached maximum size and won the match!", True, (220, 225, 235))

        reset_msg = font.render("Resetting arena for a new round...", True, (180, 185, 195))

        screen.blit(main_msg, (overlay_x + (overlay_w - main_msg.get_width()) // 2, overlay_y + 25))
        screen.blit(sub_msg, (overlay_x + (overlay_w - sub_msg.get_width()) // 2, overlay_y + 65))
        screen.blit(reset_msg, (overlay_x + (overlay_w - reset_msg.get_width()) // 2, overlay_y + 98))

    pygame.display.flip()

s.close()
pygame.quit()
