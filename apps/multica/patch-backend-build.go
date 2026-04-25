package main

import (
	"fmt"
	"os"
	"strings"
)

func main() {
	path := "server/cmd/server/router.go"
	source, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}

	before := `	r.Get("/ws", func(w http.ResponseWriter, r *http.Request) {
		realtime.HandleWebSocket(hub, mc, pr, slugResolver, w, r)
	})`

	after := `	r.Get("/ws", func(w http.ResponseWriter, r *http.Request) {
		realtime.HandleWebSocket(hub, mc, pr, slugResolver, w, r)
	})
	r.Get("/ws/", func(w http.ResponseWriter, r *http.Request) {
		realtime.HandleWebSocket(hub, mc, pr, slugResolver, w, r)
	})`

	text := string(source)
	if !strings.Contains(text, before) {
		panic("expected WebSocket route block not found")
	}
	if err := os.WriteFile(path, []byte(strings.Replace(text, before, after, 1)), 0o644); err != nil {
		panic(err)
	}
	fmt.Println("Patched backend WebSocket route to also accept /ws/")
}
