/* TCP client. Prints connection status and RTT so you can see when the firewall blocks/unblocks.
 * Build: gcc -Wall client.c -o client
 * Usage: ./client <server_ip> [port] [num_msgs] [interval_sec]                              */
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <server_ip> [port] [num_msgs] [interval_sec]\n", argv[0]);
        return 1;
    }
    const char *ip = argv[1];
    int port = argc > 2 ? atoi(argv[2]) : 5000;
    int count = argc > 3 ? atoi(argv[3]) : 10;
    double interval = argc > 4 ? atof(argv[4]) : 1.0;

    int fd = socket(AF_INET, SOCK_STREAM, 0);
    struct timeval tv = {5, 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons(port);
    if (inet_pton(AF_INET, ip, &a.sin_addr) != 1) { fprintf(stderr, "Bad IP\n"); return 1; }

    double t0 = now_ms();
    if (connect(fd, (struct sockaddr *)&a, sizeof(a)) < 0) {
        perror("[CLIENT] connection FAILED (blocked?)");
        return 1;
    }
    printf("[CLIENT] connected in %.1f ms\n", now_ms() - t0);
    fflush(stdout);

    for (int i = 1; i <= count; i++) {
        char msg[64], buf[1024];
        int mlen = snprintf(msg, sizeof(msg), "hello %d", i);
        double t = now_ms();
        if (send(fd, msg, mlen, MSG_NOSIGNAL) < 0) { perror("[CLIENT] send error"); break; }
        ssize_t n = recv(fd, buf, sizeof(buf) - 1, 0);
        if (n <= 0) { fprintf(stderr, "[CLIENT] no reply (connection closed/blocked)\n"); break; }
        buf[n] = '\0';
        while (n > 0 && (buf[n - 1] == '\n' || buf[n - 1] == '\r')) buf[--n] = '\0';
        printf("[CLIENT] sent '%s' got '%s' rtt=%.2f ms\n", msg, buf, now_ms() - t);
        fflush(stdout);
        usleep((useconds_t)(interval * 1e6));
    }
    close(fd);
    return 0;
}
