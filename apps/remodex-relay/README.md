# Remodex Relay - LazyCat App

> WebSocket relay service for Remodex pairing flow

## Usage

### Using LazyCat Deployed Relay

Before running `remodex up` to start the local bridge service, set the environment variable to specify your custom relay address:

```bash
# Set environment variable to point to LazyCat deployed relay
export REMODEX_RELAY="wss://remodex-relay.rx79.heiyu.space/relay"

# Or use the official phodex.app relay (default)
# export REMODEX_RELAY="wss://api.phodex.app/relay"

# Start the local bridge service
remodex up
```

### Access Points

- **Management UI**: `https://remodex-relay.rx79.heiyu.space/`
- **WebSocket Endpoint**: `wss://remodex-relay.rx79.heiyu.space/relay/{sessionId}`
- **Health Check**: `https://remodex-relay.rx79.heiyu.space/health`
- **Stats**: `https://remodex-relay.rx79.heiyu.space/api/stats`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REMODEX_RELAY` | `wss://api.phodex.app/relay` | Custom relay address |
| `PORT` | `3000` | HTTP server port |
| `HOST` | `0.0.0.0` | Listen address |

## Data Directory

This is a stateless service. All session data is stored in memory and does not require persistent storage.

## Security Notes

- The relay service acts as a transport layer and does not participate in end-to-end encryption
- All Remodex application payloads are encrypted via AES-256-GCM before transmission
- The relay can only see connection metadata, not plaintext content

## Upstream Project

- **GitHub**: https://github.com/Emanuele-web04/remodex
- **License**: ISC

## Version Info

- **Current Version**: 1.0.0
- **LazyCat Compatible**: Yes
