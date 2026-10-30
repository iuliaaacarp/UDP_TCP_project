// UDP Server -- Concurrent with game loop thread
#include <iostream>
#include <string>
#include <vector>
#include <map>
#include <thread>
#include <mutex>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

struct Food {
    float x, y;
    int r, g, b;
};

struct Player {
    std::string id;
    float x = 450.0f, y = 325.0f;
    float target_x = 450.0f, target_y = 325.0f;
    float radius = 20.0f;
    int score = 0;
    int r = 255, g = 0, b = 0;
    bool is_bot = false;
    int bot_timer = 0;
    sockaddr_in addr{};
    std::chrono::steady_clock::time_point last_seen;
    std::chrono::steady_clock::time_point immune_until;
};

std::map<std::string, Player> g_players;
std::vector<Food> g_foods;
std::mutex mtx;
int server_fd;

// Win Condition & Reset State
const float WIN_RADIUS = 75.0f; // Reaching radius 75 wins the match!
std::string g_winner = "";
int g_win_timer = 0; // Countdown frames after win

const int FOOD_COLORS[][3] = {
    {235, 60, 60},   // Coral Red
    {245, 135, 30},  // Bright Orange
    {245, 215, 20},  // Gold Yellow
    {40, 195, 65},   // Fresh Green
    {35, 190, 225},  // Aqua Cyan
    {50, 115, 235},  // Royal Blue
    {160, 65, 215},  // Purple
    {245, 110, 180}  // Hot Pink
};

void spawn_food(int count) {
    for (int i = 0; i < count; ++i) {
        int ci = rand() % 8;
        g_foods.push_back({
            (float)(rand() % 860 + 20),
            (float)(rand() % 610 + 20),
            FOOD_COLORS[ci][0], FOOD_COLORS[ci][1], FOOD_COLORS[ci][2]
        });
    }
}

// Safe respawn: picks a position far away from any other player
void respawn_player(Player& p) {
    float best_x = 450.0f, best_y = 325.0f;
    float max_dist = -1.0f;

    for (int attempt = 0; attempt < 10; ++attempt) {
        float cx = (float)(rand() % 800 + 50);
        float cy = (float)(rand() % 550 + 50);
        float min_d = 99999.0f;

        for (const auto& [other_id, other_p] : g_players) {
            if (other_id == p.id) continue;
            float d = std::hypot(cx - other_p.x, cy - other_p.y);
            if (d < min_d) min_d = d;
        }

        if (min_d > max_dist) {
            max_dist = min_d;
            best_x = cx;
            best_y = cy;
        }
    }

    p.x = best_x;
    p.y = best_y;
    p.target_x = best_x;
    p.target_y = best_y;
    p.radius = 20.0f;
    p.score = std::max(0, p.score / 2);
    p.immune_until = std::chrono::steady_clock::now() + std::chrono::milliseconds(2500);
}

// Reset match for everyone when a round is won
void reset_match() {
    g_winner = "";
    g_win_timer = 0;
    for (auto& [pid, p] : g_players) {
        p.score = 0;
        respawn_player(p);
    }
    g_foods.clear();
    spawn_food(45);
    std::cout << "[UDP Server] Match reset! New round begins.\n";
}

void init_bots() {
    struct BotDef { std::string name; int r, g, b; };
    std::vector<BotDef> bots = {
        {"Bot_Max", 220, 70, 70},
        {"Bot_Nova", 60, 160, 220},
        {"Bot_Spike", 160, 80, 210}
    };
    for (const auto& b : bots) {
        Player p;
        p.id = b.name;
        p.r = b.r; p.g = b.g; p.b = b.b;
        p.is_bot = true;
        p.last_seen = std::chrono::steady_clock::now();
        respawn_player(p);
        g_players[b.name] = p;
    }
}

// 30 FPS Physics & Broadcast Thread
void game_loop_thread() {
    spawn_food(45);
    init_bots();

    while (true) {
        std::this_thread::sleep_for(std::chrono::milliseconds(33)); // ~30 FPS

        std::string json_snapshot;
        std::vector<sockaddr_in> active_addrs;

        {
            std::lock_guard<std::mutex> lock(mtx);
            auto now = std::chrono::steady_clock::now();

            // Handle post-win countdown before starting a new round
            if (!g_winner.empty()) {
                g_win_timer--;
                if (g_win_timer <= 0) {
                    reset_match();
                }
            } else {
                // 1. Update AI Bots
                for (auto& [pid, p] : g_players) {
                    if (p.is_bot) {
                        p.last_seen = now;
                        p.bot_timer--;
                        if (p.bot_timer <= 0) {
                            p.target_x = (float)(rand() % 840 + 30);
                            p.target_y = (float)(rand() % 590 + 30);
                            p.bot_timer = rand() % 60 + 40;
                        }
                    }
                }

                // 2. Inactivity Timeout & Physics Movement
                for (auto it = g_players.begin(); it != g_players.end(); ) {
                    if (!it->second.is_bot &&
                        std::chrono::duration_cast<std::chrono::seconds>(now - it->second.last_seen).count() > 3) {
                        it = g_players.erase(it);
                        continue;
                    }

                    float dx = it->second.target_x - it->second.x;
                    float dy = it->second.target_y - it->second.y;
                    float dist = std::hypot(dx, dy);

                    if (dist > 5.0f) {
                        float speed = std::max(2.2f, 5.5f - (it->second.radius - 20.0f) * 0.04f);
                        it->second.x += (dx / dist) * speed;
                        it->second.y += (dy / dist) * speed;
                    }

                    it->second.x = std::max(it->second.radius, std::min(900.0f - it->second.radius, it->second.x));
                    it->second.y = std::max(it->second.radius, std::min(650.0f - it->second.radius, it->second.y));

                    if (!it->second.is_bot) {
                        active_addrs.push_back(it->second.addr);
                    }
                    ++it;
                }

                // 3. Collision: Eat Food Pellets
                for (auto& [pid, player] : g_players) {
                    for (auto f_it = g_foods.begin(); f_it != g_foods.end(); ) {
                        float dist = std::hypot(player.x - f_it->x, player.y - f_it->y);
                        if (dist < player.radius) {
                            player.radius = std::min(player.radius + 0.8f, WIN_RADIUS);
                            player.score += 1;
                            f_it = g_foods.erase(f_it);

                            int ci = rand() % 8;
                            g_foods.push_back({
                                (float)(rand() % 860 + 20),
                                (float)(rand() % 610 + 20),
                                FOOD_COLORS[ci][0], FOOD_COLORS[ci][1], FOOD_COLORS[ci][2]
                            });

                            // Check Win Condition!
                            if (player.radius >= WIN_RADIUS && g_winner.empty()) {
                                g_winner = player.id;
                                g_win_timer = 120; // 4 seconds at 30 FPS
                                std::cout << "[UDP Server] " << g_winner << " REACHED FULL SIZE AND WON!\n";
                            }
                        } else {
                            ++f_it;
                        }
                    }
                }

                // 4. Collision: Larger players eat smaller players
                for (auto& [id1, p1] : g_players) {
                    for (auto& [id2, p2] : g_players) {
                        if (id1 == id2) continue;
                        if (now < p2.immune_until) continue;

                        float dist = std::hypot(p1.x - p2.x, p1.y - p2.y);
                        if (dist < p1.radius && p1.radius > p2.radius * 1.15f) {
                            p1.radius = std::min(p1.radius + (p2.radius * 0.25f), WIN_RADIUS);
                            p1.score += 15;
                            std::cout << "[UDP Server] " << id1 << " ate " << id2 << "!\n";
                            respawn_player(p2);

                            // Check Win Condition!
                            if (p1.radius >= WIN_RADIUS && g_winner.empty()) {
                                g_winner = p1.id;
                                g_win_timer = 120;
                                std::cout << "[UDP Server] " << g_winner << " REACHED FULL SIZE AND WON!\n";
                            }
                        }
                    }
                }
            }

            // 5. Build JSON snapshot (with winner flag)
            json_snapshot = "{\"winner\":\"" + g_winner + "\",\"players\":{";
            bool first_p = true;
            for (auto const& [pid, p] : g_players) {
                if (!first_p) json_snapshot += ",";
                bool is_immune = (now < p.immune_until);
                json_snapshot += "\"" + pid + "\":{"
                    "\"x\":" + std::to_string((int)p.x) +
                    ",\"y\":" + std::to_string((int)p.y) +
                    ",\"r\":" + std::to_string((int)p.radius) +
                    ",\"score\":" + std::to_string(p.score) +
                    ",\"immune\":" + (is_immune ? "1" : "0") +
                    ",\"color\":[" + std::to_string(p.r) + "," + std::to_string(p.g) + "," + std::to_string(p.b) + "]}";
                first_p = false;
            }
            json_snapshot += "},\"food\":[";
            bool first_f = true;
            for (const auto& f : g_foods) {
                if (!first_f) json_snapshot += ",";
                json_snapshot += "{\"x\":" + std::to_string((int)f.x) +
                                 ",\"y\":" + std::to_string((int)f.y) +
                                 ",\"c\":[" + std::to_string(f.r) + "," + std::to_string(f.g) + "," + std::to_string(f.b) + "]}";
                first_f = false;
            }
            json_snapshot += "]}";
        }

        // Broadcast to all active clients
        for (const auto& addr : active_addrs) {
            sendto(server_fd, json_snapshot.c_str(), json_snapshot.length(), 0,
                   (struct sockaddr*)&addr, sizeof(addr));
        }
    }
}

int main() {
    srand(time(nullptr));
    // 1. Create UDP socket
    server_fd = socket(AF_INET, SOCK_DGRAM, 0);

    // 2. Bind to 0.0.0.0:5555 ("0.0.0.0" receive anything from the OS, IP > 1024)
    sockaddr_in server_addr{};
    server_addr.sin_family = AF_INET;
    server_addr.sin_port = htons(5555);
    server_addr.sin_addr.s_addr = INADDR_ANY; // 0.0.0.0
    bind(server_fd, (struct sockaddr*)&server_addr, sizeof(server_addr));

    std::cout << "[UDP Server with Win Condition] Listening on port 5555...\n";

    // Launch game loop thread
    std::thread(game_loop_thread).detach();

    char buff[1024];
    while (true) {
        sockaddr_in client_addr{};
        socklen_t addr_len = sizeof(client_addr);

        // recvfrom -> message + address
        int bytes = recvfrom(server_fd, buff, sizeof(buff) - 1, 0,
                             (struct sockaddr*)&client_addr, &addr_len);
        if (bytes <= 0) continue;
        buff[bytes] = '\0';

        // Parse: "MOVE:<pid>:<x>:<y>:<r>:<g>:<b>"
        std::string msg(buff);
        if (msg.rfind("MOVE:", 0) == 0) {
            char pid[64];
            float tx, ty;
            int r, g, b;
            if (sscanf(msg.c_str(), "MOVE:%63[^:]:%f:%f:%d:%d:%d", pid, &tx, &ty, &r, &g, &b) == 6) {
                std::lock_guard<std::mutex> lock(mtx);
                auto& p = g_players[pid];
                if (p.id.empty()) {
                    p.id = pid;
                    respawn_player(p);
                }
                p.target_x = tx;
                p.target_y = ty;
                p.r = r; p.g = g; p.b = b;
                p.addr = client_addr;
                p.last_seen = std::chrono::steady_clock::now();
            }
        }
    }

    close(server_fd);
    return 0;
}
