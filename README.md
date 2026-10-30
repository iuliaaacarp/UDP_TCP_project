# TCP & UDP Network Game Projects

[![C++17](https://img.shields.io/badge/C++-17-00599C?logo=c%2B%2B)](https://isocpp.org/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED?logo=docker)](https://www.docker.com/)
[![Pygame](https://img.shields.io/badge/GUI-Pygame-green)](https://www.pygame.org/)
[![Sockets](https://img.shields.io/badge/Networking-BSD%20Sockets-orange)]()

A comprehensive network programming project demonstrating and contrasting **TCP (`SOCK_STREAM`)** and **UDP (`SOCK_DGRAM`)** socket communication through two real-time, multi-client multiplayer games:

1. **Draw & Guess (TCP):** A turn-based Pictionary game with a room lobby, host management, dynamic turn rotation, live word hints, a 12-color drawing palette, and chat-based guessing with scoring.
2. **Agar.io Arena (UDP):** A fast-paced real-time arena with smooth vector steering, colorful food consumption, server-side AI bots, safe respawns with spawn protection shields, a live leaderboard, and a full-size victory condition.

Both game backends are authored in **modern C++17** running inside **Docker containers** with thread concurrency, while the graphical frontends are written in **Python (Pygame)** running natively on the host machine.

---

## Architecture Overview

```
 ┌───────────────────────────────────────────────────────────────┐
 │                   HOST MACHINE (macOS / Linux / Windows)      │
 │                                                               │
 │   ┌───────────────────────────┐   ┌───────────────────────┐   │
 │   │  TCP Client (Alice)       │   │  UDP Client (Bob)     │   │
 │   │  Python / Pygame GUI      │   │  Python / Pygame GUI  │   │
 │   └─────────────┬─────────────┘   └───────────┬───────────┘   │
 └─────────────────┼─────────────────────────────┼───────────────┘
                   │ TCP :6666                   │ UDP :5555
                   │ (Stream)                    │ (Datagrams)
 ┌─────────────────▼─────────────────────────────▼───────────────┐
 │                   DOCKER ENGINE / CONTAINER MAPPING           │
 │                                                               │
 │   ┌───────────────────────────┐   ┌───────────────────────┐   │
 │   │  tcp_draw_server          │   │  udp_agario_server    │   │
 │   │  C++17 Concurrent Server  │   │  C++17 Engine Server  │   │
 │   │  Thread-per-Client        │   │  30 FPS State Tick    │   │
 │   │  Bound: 0.0.0.0:6666      │   │  Bound: 0.0.0.0:5555  │   │
 │   └───────────────────────────┘   └───────────────────────┘   │
 └───────────────────────────────────────────────────────────────┘
```

---

## Key Comparison: TCP vs. UDP Implementation

| Feature | Project 1: Draw & Guess (TCP) | Project 2: Agar.io Arena (UDP) |
| :--- | :--- | :--- |
| **Socket Type** | `SOCK_STREAM` (Connection-oriented) | `SOCK_DGRAM` (Connectionless) |
| **Connection Setup** | 3-way Handshake (`connect()` $\leftrightarrow$ `accept()`) | None (immediate `sendto()` / `recvfrom()`) |
| **Descriptor Model** | 1 listening socket + 1 socket per connected client | 1 single socket handles all clients |
| **Concurrency Pattern** | **Thread-per-Client:** `std::thread` per accepted connection | **Engine-Worker:** Dedicated receiver thread + 30 FPS broadcast thread |
| **Synchronization** | `std::mutex` + `std::lock_guard` on client registry | `std::mutex` + `std::lock_guard` on world state |
| **Message Framing** | **Stream Delimiting:** Required (`\n`) to prevent merged packets | **Datagram Preserved:** Each packet is an isolated message |
| **Reliability Model** | 100% Guaranteed, ordered, retransmitted on loss | Best-effort; stale packets are discarded, newest state replaces old |
| **Disconnection** | **Deterministic:** `recv() <= 0` triggered by client exit | **Implicit:** 3-second heartbeat / inactivity timeout |
| **Docker Port Spec** | `"6666:6666"` (Defaults to TCP) | `"5555:5555/udp"` (Requires explicit `/udp` flag) |

---

## Project 1: Draw & Guess (TCP)

### 1. Network Architecture
* **Connection Lifecycle:** Clients initiate connection via `s.connect(("127.0.0.1", 6666))`. The C++ server unblocks from `accept()`, generating a unique file descriptor (`client_fd`) and spawning an isolated thread (`handle_client`).
* **Message Framing:** Because TCP is a continuous byte stream without packet boundaries, messages are delimited with `\n`. The receiver accumulates chunks into a buffer and extracts lines individually:
  ```text
  Client sends: "DRAW:120:300:125:310:red\n"
  Server splits by '\n' and relays to all other connected clients
  ```
* **Thread Safety:** Client descriptors and scores are stored in `std::vector<ClientInfo>` protected by a `std::mutex`.
* **Clean Disconnection:** When a client window closes, the OS sends a TCP `FIN` packet. The server's `recv()` returns `0`, initiating thread cleanup, socket closure, and host reassignment if needed.

### 2. Game Features
* **Lobby & Host System:** The first player to connect automatically becomes the **Host**. A waiting room displays the real-time connected player list (`1. Alice (Host) (You)`, `2. Bob`, etc.).
* **"Start Game" Control:** Only the Host has the **Start Game** button, enabled once at least 2 players have joined.
* **Turn Rotation & Roles:**
  * **The Drawer:** Receives the secret word (e.g., `ROLE:DRAWER:PIZZA\n`). The canvas and palette become active.
  * **The Guessers:** Receive masked hints (e.g., `ROLE:GUESSER:Alice:_ _ _ _ _ (5 letters)\n`). Canvas is locked; they type guesses into the chat box.
* **12-Color Palette & Tools:** Black, Grey, White (**Eraser** with a thicker 10px brush), Red, Orange, Yellow, Green, Cyan, Blue, Purple, Pink, Brown, plus a **Clear Canvas** button.
* **Chat with Word-Wrapping:** Long chat messages, hints, and scoreboards dynamically wrap across lines so text never clips.
* **Scoring:** Correct guess awards **+10 pts** to the guesser, **+5 pts** to the drawer, prints a live scoreboard, and rotates the Drawer role after a 2-second transition.

---

## Project 2: Agar.io Arena (UDP)

### 1. Network Architecture
* **Connectionless Datagrams:** No handshake or connection establishment. Clients blast their inputs at 60 FPS using `sendto(msg, ("127.0.0.1", 5555))`.
* **Client Identification via Endpoint:** The server's single socket reads incoming datagrams with `recvfrom()`, extracting the payload and the client's `(IP, Port)` address (`sockaddr_in`).
* **State Replication at 30 FPS:** A dedicated game engine thread ticks every 33ms, processes physics, food eating, bot behaviors, and win conditions, and broadcasts a complete JSON snapshot to all active client addresses.
* **Packet-Loss Resilience:** If a UDP packet drops under network congestion, no retransmission is requested. The subsequent packet arriving 33ms later automatically provides the newest coordinates and scores.
* **Inactivity Timeout (Keep-Alive):** Every player records `last_seen = now`. If no packet arrives from a client for $> 3$ seconds, the server removes them from memory.

### 2. Game Features
* **Normalized Vector Controls:** Blobs move towards the mouse cursor using normalized directional vectors:
  $$\vec{v} = \frac{\Delta\vec{p}}{\|\Delta\vec{p}\|} \times \text{speed}$$
  Smaller blobs move faster (5.5 px/frame), while larger blobs move slightly slower (2.2 px/frame).
* **Multi-Colored Food:** 45 food pellets spawn across the arena in vibrant colors (Coral, Orange, Gold, Green, Aqua, Blue, Purple, Pink) and respawn immediately when consumed.
* **Autonomous Server-Side Bots:** 3 AI bots (`Bot_Max`, `Bot_Nova`, `Bot_Spike`) roam the arena, eat food, grow, and interact with human players.
* **Safe Respawn & Immunity Shield:**
  * When a player is eaten, the server tests 10 candidate locations and spawns them **farthest away from active threats**.
  * Input targets are reset so the blob does not pull back towards where it died.
  * Players receive a **2.5-second Spawn Protection Shield** (cyan ring) preventing them from being eaten immediately.
* **Side Leaderboard:** A top-right leaderboard ranks all players and bots in real time by score, highlighting your position.
* **Victory Condition:** Reaching full size (**radius = 75**) triggers a victory overlay (`VICTORY! YOU REACHED FULL SIZE!`), pauses for 4 seconds, and resets the arena for a new round.
* **Size Progress Bar:** A progress bar at the bottom center tracks percentage towards the victory size.

---

## Directory Structure

```text
UDP_TCP_project/
├── docker-compose.yml          # Container orchestration (ports 6666/tcp & 5555/udp)
├── requirements.txt            # Python dependencies (pygame)
├── README.md                   # Project documentation
├── tcp_draw_guess/
│   ├── Dockerfile              # C++17 build image with -pthread
│   ├── server.cpp              # TCP Multi-client server (threads, mutex, lobby, turns)
│   └── client.py               # TCP Client (Pygame canvas, palette, wrapped chat)
└── udp_agario/
    ├── Dockerfile              # C++17 build image
    ├── server.cpp              # UDP Server (30 FPS broadcast, bots, physics, win logic)
    └── client.py               # UDP Client (Pygame arena, leaderboard, progress bar)
```

---

## Prerequisites

1. **Docker & Docker Desktop:** [Install Docker](https://www.docker.com/products/docker-desktop/)
2. **Python 3.10+:** [Install Python](https://www.python.org/downloads/)
3. **Pip & Virtual Environment:** Recommended for local Python GUI execution.

---

## Setup & Running Guide

### Step 1: Clone and Prepare
```bash
git clone <your-repo-url>
cd UDP_TCP_project
```

### Step 2: Install Python Client Dependencies
```bash
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3: Start the C++ Servers with Docker
Build and launch both servers in the background:
```bash
docker compose up --build -d
```
Verify that both containers are running:
```bash
docker compose ps
```
You should see:
* `udp_agario_server` listening on `0.0.0.0:5555->5555/udp`
* `tcp_draw_server` listening on `0.0.0.0:6666->6666/tcp`

To inspect live server logs:
```bash
docker compose logs -f
```

---

### Step 4: Run the Games

#### Testing TCP Draw & Guess (Multiple Clients):
Open 2 or 3 separate terminal tabs:

* **Terminal 1 (Host):**
  ```bash
  python3 tcp_draw_guess/client.py Alice
  ```
* **Terminal 2:**
  ```bash
  python3 tcp_draw_guess/client.py Bob
  ```
* **Terminal 3 (Optional):**
  ```bash
  python3 tcp_draw_guess/client.py Charlie
  ```
1. Alice (Host) sees all connected players in the **Game Lobby**.
2. When ready, Alice clicks **`Start Game`**.
3. The server assigns roles: Drawer draws on the canvas using colors/eraser; Guessers type guesses in the chat box.

---

#### Testing UDP Agar.io Arena (Multiple Clients):
Open 2 or 3 separate terminal tabs:

* **Terminal 1:**
  ```bash
  python3 udp_agario/client.py Alice
  ```
* **Terminal 2:**
  ```bash
  python3 udp_agario/client.py Bob
  ```
1. Steer your circle by moving the mouse.
2. Consume colorful pellets to grow larger and watch your **Size Progress Bar** increase.
3. Compete against other players and autonomous server bots (`Bot_Max`, `Bot_Nova`, `Bot_Spike`).
4. Avoid larger blobs; collide with smaller blobs to consume them.
5. Reach radius 75 to trigger the match **Victory Condition**!

---

### Step 5: Stopping the Containers
When finished testing:
```bash
docker compose down
```

---

## Technical Notes

### Why bind to `0.0.0.0` inside Docker?
If a server inside a container binds to `127.0.0.1` (localhost), it only listens on the container's internal loopback interface. Docker's port proxy forwards host traffic to the container's external network interface (`eth0`). Binding to `0.0.0.0` (`INADDR_ANY`) ensures the server accepts traffic routed across the bridge network.

### Why is `/udp` required in `docker-compose.yml`?
By default, Docker port mappings (`"5555:5555"`) allocate TCP listeners only. Specifying `"5555:5555/udp"` explicitly instructs the Docker proxy and iptables to establish UDP NAT rules, forwarding incoming UDP datagrams to the container.

---

## License
Distributed under the MIT License. Feel free to use and modify for educational and portfolio purposes.
