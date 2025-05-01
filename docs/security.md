# Security Overview

## JWT Authentication Flow

```mermaid
sequenceDiagram
    participant Client
    participant Gateway
    participant Redis
    Client->>Gateway: POST /auth/login { username }
    Gateway->>Gateway: generate access_token, refresh_token (HS256)
    Gateway-->>Client: { access_token, refresh_token }
    Client->>Gateway: GET /protected (Auth: Bearer access_token)
    Gateway->>Gateway: jwt.decode → verify “type” = access
    Gateway->>Redis: GET blacklist:<jti> → nil
    Gateway-->>Client: 200 OK + payload
