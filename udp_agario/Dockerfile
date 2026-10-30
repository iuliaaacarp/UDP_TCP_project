FROM gcc:latest

WORKDIR /app

# Copy C++ server source code
COPY server.cpp .

# Compile C++17 with multi-threading (pthread)
RUN g++ -std=c++17 -pthread server.cpp -o server_udp

# Document UDP port
EXPOSE 5555/udp

# Run the UDP server
CMD ["./server_udp"]
