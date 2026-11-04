/* Centralized security-event logger (TCP). Run on the logger host (e.g., h4).
 * Receives newline-delimited JSON events, adds a timestamp, appends to security_events.log
 * Build: gcc -Wall -pthread logger_server.c -o logger_server
 * Usage: ./logger_server [port]                                                        */
#include <arpa/inet.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define LOGFILE "security_events.log"
#define BUFSZ 2048

static pthread_mutex_t log_mtx = PTHREAD_MUTEX_INITIALIZER;

struct conn_info { int fd; char ip[INET_ADDRSTRLEN]; };

static void write_event(const char *peer, const char *line) {
    char ts[32];
    time_t t = time(NULL);
    struct tm tmv;
    localtime_r(&t, &tmv);
    strftime(ts, sizeof(ts), "%Y-%m-%d %H:%M:%S", &tmv);

    pthread_mutex_lock(&log_mtx);
    FILE *f = fopen(LOGFILE, "a");
    if (f) {
        fprintf(f, "{\"received_at\":\"%s\",\"reporter\":\"%s\",\"event\":%s}\n", ts, peer, line);
        fclose(f);
    }
    printf("[LOGGER] {\"received_at\":\"%s\",\"reporter\":\"%s\",\"event\":%s}\n", ts, peer, line);
    fflush(stdout);
    pthread_mutex_unlock(&log_mtx);
}

static void *handle(void *arg) {
    struct conn_info ci = *(struct conn_info *)arg;
    free(arg);
    char buf[BUFSZ], pending[BUFSZ * 4];
    size_t plen = 0;
    ssize_t n;
    while ((n = recv(ci.fd, buf, sizeof(buf), 0)) > 0) {
        if (plen + n >= sizeof(pending)) plen = 0;      /* drop overflow, keep simple */
        memcpy(pending + plen, buf, n);
        plen += n;
        char *nl;
        while ((nl = memchr(pending, '\n', plen)) != NULL) {
            size_t linelen = nl - pending;
            pending[linelen] = '\0';
            if (linelen > 0) write_event(ci.ip, pending);
            memmove(pending, nl + 1, plen - linelen - 1);
            plen -= linelen + 1;
        }
    }
    close(ci.fd);
    return NULL;
}

int main(int argc, char *argv[]) {
    int port = argc > 1 ? atoi(argv[1]) : 6000;
    int srv = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(port);
    if (bind(srv, (struct sockaddr *)&addr, sizeof(addr)) < 0) { perror("bind"); return 1; }
    listen(srv, 20);
    printf("[LOGGER] listening on 0.0.0.0:%d\n", port);
    fflush(stdout);

    while (1) {
        struct sockaddr_in cli;
        socklen_t len = sizeof(cli);
        int fd = accept(srv, (struct sockaddr *)&cli, &len);
        if (fd < 0) continue;
        struct conn_info *ci = malloc(sizeof(*ci));
        ci->fd = fd;
        inet_ntop(AF_INET, &cli.sin_addr, ci->ip, sizeof(ci->ip));
        pthread_t th;
        pthread_create(&th, NULL, handle, ci);
        pthread_detach(th);
    }
}
