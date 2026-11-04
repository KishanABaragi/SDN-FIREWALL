/* Application TCP server. Run on the server host (e.g., h3).
 * One thread per client, ACKs every message, optionally reports CONNECT/DISCONNECT
 * events to the central logger.
 * Build: gcc -Wall -pthread app_server.c -o app_server
 * Usage: ./app_server [port] [logger_ip] [logger_port]                              */
#include <arpa/inet.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

static int PORT = 5000;
static char LOGGER_IP[64] = "";
static int LOGGER_PORT = 6000;

struct conn_info { int fd; char ip[INET_ADDRSTRLEN]; int sport; };

/* Send one JSON event line to the logger. Fails quietly if the logger is unreachable. */
static void report(const char *type, const char *ip, int sport, const char *detail) {
    if (LOGGER_IP[0] == '\0') return;
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    struct timeval tv = {2, 0};
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons(LOGGER_PORT);
    inet_pton(AF_INET, LOGGER_IP, &a.sin_addr);
    if (connect(fd, (struct sockaddr *)&a, sizeof(a)) < 0) {
        fprintf(stderr, "[SERVER] logger unreachable\n");
        close(fd);
        return;
    }
    char ev[512];
    int len = snprintf(ev, sizeof(ev),
        "{\"time\":%ld,\"type\":\"%s\",\"src_ip\":\"%s\",\"src_port\":%d,\"dst_port\":%d,\"detail\":\"%s\"}\n",
        (long)time(NULL), type, ip, sport, PORT, detail);
    send(fd, ev, len, MSG_NOSIGNAL);
    close(fd);
}

static void *handle(void *arg) {
    struct conn_info ci = *(struct conn_info *)arg;
    free(arg);
    printf("[SERVER] connected: %s:%d\n", ci.ip, ci.sport);
    fflush(stdout);
    report("CONNECT", ci.ip, ci.sport, "");

    char buf[1024];
    ssize_t n;
    while ((n = recv(ci.fd, buf, sizeof(buf) - 1, 0)) > 0) {
        buf[n] = '\0';
        while (n > 0 && (buf[n - 1] == '\n' || buf[n - 1] == '\r')) buf[--n] = '\0';
        printf("[SERVER] %s:%d -> %s\n", ci.ip, ci.sport, buf);
        fflush(stdout);
        char ack[1100];
        int len = snprintf(ack, sizeof(ack), "ACK: %s\n", buf);
        send(ci.fd, ack, len, MSG_NOSIGNAL);
    }
    close(ci.fd);
    printf("[SERVER] disconnected: %s:%d\n", ci.ip, ci.sport);
    fflush(stdout);
    report("DISCONNECT", ci.ip, ci.sport, "");
    return NULL;
}

int main(int argc, char *argv[]) {
    if (argc > 1) PORT = atoi(argv[1]);
    if (argc > 2) { strncpy(LOGGER_IP, argv[2], sizeof(LOGGER_IP) - 1); }
    if (argc > 3) LOGGER_PORT = atoi(argv[3]);

    int srv = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(PORT);
    if (bind(srv, (struct sockaddr *)&addr, sizeof(addr)) < 0) { perror("bind"); return 1; }
    listen(srv, 50);
    printf("[SERVER] listening on 0.0.0.0:%d\n", PORT);
    fflush(stdout);

    while (1) {
        struct sockaddr_in cli;
        socklen_t len = sizeof(cli);
        int fd = accept(srv, (struct sockaddr *)&cli, &len);
        if (fd < 0) continue;
        struct conn_info *ci = malloc(sizeof(*ci));
        ci->fd = fd;
        ci->sport = ntohs(cli.sin_port);
        inet_ntop(AF_INET, &cli.sin_addr, ci->ip, sizeof(ci->ip));
        pthread_t th;
        pthread_create(&th, NULL, handle, ci);
        pthread_detach(th);
    }
}
