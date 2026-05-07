package api

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"time"

	"adbs/api/router"
)

// listenPort 默认 18081，可用环境变量 ADBS_PORT 覆盖（例如 8081）。
func listenPort() int {
	p := os.Getenv("ADBS_PORT")
	if p == "" {
		return 18081
	}
	n, err := strconv.Atoi(p)
	if err != nil || n < 1 || n > 65535 {
		log.Printf("invalid ADBS_PORT=%q, using 18081", p)
		return 18081
	}
	return n
}

func Init() {
	r := router.Init()
	port := listenPort()

	s := &http.Server{
		Addr:           fmt.Sprintf(":%d", port),
		Handler:        r,
		ReadTimeout:    10 * time.Second,
		WriteTimeout:   10 * time.Second,
		MaxHeaderBytes: 1 << 20,
	}

	go func() {
		if err := s.ListenAndServe(); err != nil {
			log.Printf("Listen Error: %s\n", err)
		}
	}()

	quit := make(chan os.Signal)
	signal.Notify(quit, os.Interrupt)
	<-quit

	log.Println("Shutdown Server ...")

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := s.Shutdown(ctx); err != nil {
		log.Fatal("Server Shutdown:", err)
	}

	log.Println("Server exiting")
}
