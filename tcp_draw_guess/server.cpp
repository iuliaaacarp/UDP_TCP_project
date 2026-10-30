// TCP Server -- Concurrent with threads
#include <iostream>
#include <string>
#include <vector>
#include <thread>
#include <mutex>
#include <algorithm>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>

struct ClientInfo {
    int fd;
    std::string username;
    int score = 0;
    bool is_host = false;
};

std::vector<ClientInfo> g_clients;
std::mutex mtx;

const std::vector<std::string> WORDS = {
    "cat", "dog", "sun", "car", "tree", "house", "fish", "star", "boat", "bird", "apple", "pizza", "ball"
};

int g_drawer_index = 0;
std::string g_current_word = "";
bool g_game_active = false;

void send_msg(int fd, const std::string& msg) {
    send(fd, msg.c_str(), msg.length(), 0);
}

void broadcast(const std::string& msg, int sender_fd = -1) {
    for (const auto& client : g_clients) {
        if (client.fd != sender_fd) {
            send_msg(client.fd, msg);
        }
    }
}

std::string make_hint(const std::string& word) {
    std::string hint = "";
    for (size_t i = 0; i < word.length(); ++i) hint += "_ ";
    hint += "(" + std::to_string(word.length()) + " letters)";
    return hint;
}

void broadcast_lobby() {
    if (g_clients.empty()) return;
    std::string host_name = g_clients[0].username;
    std::string player_list = "";
    for (size_t i = 0; i < g_clients.size(); ++i) {
        if (i > 0) player_list += ",";
        player_list += g_clients[i].username;
        if (g_clients[i].is_host) player_list += " (Host)";
    }
    for (const auto& client : g_clients) {
        send_msg(client.fd, std::string("HOST:") + (client.is_host ? "1\n" : "0\n"));
        send_msg(client.fd, "LOBBY:" + host_name + ":" + player_list + "\n");
    }
}

void start_new_round() {
    if (g_clients.size() < 2) {
        g_game_active = false;
        broadcast_lobby();
        broadcast("CLEAR\n");
        return;
    }

    g_drawer_index = g_drawer_index % g_clients.size();
    ClientInfo& drawer = g_clients[g_drawer_index];
    g_current_word = WORDS[rand() % WORDS.size()];
    g_game_active = true;

    broadcast("CLEAR\n");
    send_msg(drawer.fd, "ROLE:DRAWER:" + g_current_word + "\n");

    std::string hint = make_hint(g_current_word);
    for (const auto& client : g_clients) {
        if (client.fd != drawer.fd) {
            send_msg(client.fd, "ROLE:GUESSER:" + drawer.username + ":" + hint + "\n");
        }
    }
    broadcast("CHAT:[Server] --- Round Started! " + drawer.username + " is drawing! ---\n");
}

// TCP -- concurrent: 1 thread per client
void handle_client(int client_fd) {
    char buff[1024];
    std::string stream = "";
    std::string username = "Guest";

    while (true) {
        int bytes = recv(client_fd, buff, sizeof(buff) - 1, 0);
        if (bytes <= 0) break; // Client disconnected
        buff[bytes] = '\0';
        stream += buff;

        // Message framing with '\n'
        size_t pos = 0;
        while ((pos = stream.find('\n')) != std::string::npos) {
            std::string line = stream.substr(0, pos);
            stream.erase(0, pos + 1);

            if (line.rfind("NAME:", 0) == 0) {
                username = line.substr(5);
                std::lock_guard<std::mutex> lock(mtx);
                for (auto& c : g_clients) {
                    if (c.fd == client_fd) c.username = username;
                }
                broadcast("CHAT:[Server] " + username + " entered the lobby.\n");
                if (!g_game_active) broadcast_lobby();
                else {
                    ClientInfo& drawer = g_clients[g_drawer_index % g_clients.size()];
                    send_msg(client_fd, "ROLE:GUESSER:" + drawer.username + ":" + make_hint(g_current_word) + "\n");
                }
            }
            else if (line.rfind("START_GAME", 0) == 0) {
                std::lock_guard<std::mutex> lock(mtx);
                if (g_clients.size() >= 2 && !g_game_active) {
                    broadcast("CHAT:[Server] Host started the game!\n");
                    start_new_round();
                }
            }
            else if (line.rfind("DRAW:", 0) == 0) {
                std::lock_guard<std::mutex> lock(mtx);
                if (g_game_active && g_clients[g_drawer_index % g_clients.size()].fd == client_fd) {
                    broadcast(line + "\n", client_fd);
                }
            }
            else if (line.rfind("CLEAR", 0) == 0) {
                std::lock_guard<std::mutex> lock(mtx);
                if (g_game_active && g_clients[g_drawer_index % g_clients.size()].fd == client_fd) {
                    broadcast("CLEAR\n");
                }
            }
            else if (line.rfind("GUESS:", 0) == 0) {
                std::string guess = line.substr(6);
                std::string guess_lower = guess;
                std::transform(guess_lower.begin(), guess_lower.end(), guess_lower.begin(), ::tolower);

                std::lock_guard<std::mutex> lock(mtx);
                int drawer_fd = g_game_active ? g_clients[g_drawer_index % g_clients.size()].fd : -1;

                if (client_fd == drawer_fd) continue;

                if (g_game_active && guess_lower == g_current_word) {
                    g_clients[g_drawer_index % g_clients.size()].score += 5;
                    for (auto& c : g_clients) {
                        if (c.fd == client_fd) c.score += 10;
                    }
                    broadcast("CHAT:[Winner] " + username + " guessed the word '" + g_current_word + "'! (+10 pts)\n");

                    std::string scores = "CHAT:[Scoreboard] ";
                    for (const auto& c : g_clients) scores += c.username + ": " + std::to_string(c.score) + " pts | ";
                    broadcast(scores + "\n");

                    g_drawer_index = (g_drawer_index + 1) % g_clients.size();
                    std::thread([]() {
                        std::this_thread::sleep_for(std::chrono::seconds(2));
                        std::lock_guard<std::mutex> lock(mtx);
                        start_new_round();
                    }).detach();
                } else {
                    broadcast("CHAT:[" + username + "] " + guess + "\n");
                }
            }
        }
    }

    // Cleanup
    {
        std::lock_guard<std::mutex> lock(mtx);
        bool was_host = false;
        bool was_drawer = false;

        for (const auto& c : g_clients) {
            if (c.fd == client_fd && c.is_host) was_host = true;
        }
        if (g_game_active && g_clients[g_drawer_index % g_clients.size()].fd == client_fd) {
            was_drawer = true;
        }

        g_clients.erase(
            std::remove_if(g_clients.begin(), g_clients.end(),
                           [client_fd](const ClientInfo& c) { return c.fd == client_fd; }),
            g_clients.end()
        );

        broadcast("CHAT:[Server] " + username + " left the game.\n");

        if (was_host && !g_clients.empty()) {
            g_clients[0].is_host = true;
        }

        if (g_clients.size() < 2) {
            g_game_active = false;
            broadcast_lobby();
        } else if (was_drawer && g_game_active) {
            start_new_round();
        }
    }
    close(client_fd);
}

int main() {
    srand(time(nullptr));
    // 1. Create TCP socket
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    // 2. Bind to 0.0.0.0:6666
    sockaddr_in server_addr{};
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(6666);
    server_addr.sin_addr.s_addr = INADDR_ANY; // 0.0.0.0
    bind(server_fd, (struct sockaddr*)&server_addr, sizeof(server_addr));

    // 3. Listen
    listen(server_fd, 20);
    std::cout << "[TCP Server] Listening on port 6666...\n";

    // 4. Accept loop (TCP -- concurrent)
    while (true) {
        sockaddr_in client_addr{};
        socklen_t addr_len = sizeof(client_addr);
        int client_fd = accept(server_fd, (struct sockaddr*)&client_addr, &addr_len);

        if (client_fd >= 0) {
            {
                std::lock_guard<std::mutex> lock(mtx);
                bool is_first = g_clients.empty();
                g_clients.push_back({client_fd, "Guest", 0, is_first});
            }
            // Spawn concurrent thread for this client
            std::thread(handle_client, client_fd).detach();
        }
    }

    close(server_fd);
    return 0;
}
