# ---- Base Node Stage (for dependencies and building) ----
    FROM node:20-alpine AS base
    WORKDIR /app
    
    # Install pnpm globally in this base stage, so it's available in subsequent stages
    RUN npm install -g pnpm
    
    # ---- Dependencies Stage ----
    # This stage installs all dependencies, including devDependencies needed for building
    # and native addon compilation.
    FROM base AS deps
    WORKDIR /app
    
    # Install Python and build tools needed by node-gyp (e.g., for bufferutil, utf-8-validate)
    # For alpine, these are python3, make, and g++ (g++ is typically part of 'build-base' meta-package)
    RUN apk add --no-cache python3 make g++
    
    # Copy only package.json and pnpm-lock.yaml to leverage Docker cache
    COPY package.json pnpm-lock.yaml ./
    
    # Install all dependencies (including devDependencies)
    # --frozen-lockfile ensures pnpm uses the versions specified in the lockfile
    RUN pnpm install --frozen-lockfile
    
    # ---- Builder Stage ----
    # This stage builds the Next.js application.
    # It inherits from 'base' which doesn't have python/g++ to keep it lean if those aren't needed by the build script itself,
    # but it copies the already compiled node_modules from the 'deps' stage.
    FROM base AS builder
    WORKDIR /app
    
    # Copy the compiled node_modules from the 'deps' stage
    COPY --from=deps /app/node_modules ./node_modules
    
    # Copy the rest of the application source code
    COPY . .
    
    # Set build-time ARGs for backend URLs if you want them baked in during the build.
    # It's generally better to set these at runtime via environment variables in docker-compose.yml.
    # ARG NEXT_PUBLIC_BACKEND_API_URL=/v1
    # ARG NEXT_PUBLIC_BACKEND_WS_URL=/v1/stream
    # ENV NEXT_PUBLIC_BACKEND_API_URL=${NEXT_PUBLIC_BACKEND_API_URL}
    # ENV NEXT_PUBLIC_BACKEND_WS_URL=${NEXT_PUBLIC_BACKEND_WS_URL}
    
    # Build the Next.js application.
    # The `migrate` script is part of the build command in your package.json.
    # Ensure POSTGRES_URL is available if needed at build time.
    # If migrate is not strictly needed for *just* the frontend build,
    # you could remove it from the build script in package.json for Docker builds.
    # ARG POSTGRES_URL
    # ENV POSTGRES_URL=${POSTGRES_URL}
    RUN pnpm run build
    
    # ---- Runner Stage (Final Production Image) ----
    # This stage creates the final, lean image for production.
    # It inherits from 'base' (node:20-alpine) for a small image size.
    FROM base AS runner
    WORKDIR /app
    
    ENV NODE_ENV=production
    
    # We need pnpm to run `pnpm start`.
    # If it wasn't installed in the 'base' stage globally, you'd install it here.
    # COPY --from=deps /app/package.json /app/pnpm-lock.yaml ./
    # RUN pnpm install -g pnpm # Already in base stage
    # RUN pnpm install --prod --frozen-lockfile # This would rebuild prod deps.
                                              # It's safer to copy already compiled ones.
    
    # Copy the node_modules (including compiled native addons) from the 'deps' stage.
    # This ensures that modules like bufferutil don't need to be recompiled in this lean stage.
    COPY --from=deps /app/node_modules ./node_modules
    
    # Copy built artifacts from the 'builder' stage
    COPY --from=builder /app/.next ./.next
    COPY --from=builder /app/public ./public
    COPY --from=builder /app/next.config.ts ./
    # If your package.json is needed by `pnpm start` (it usually is to find the start script)
    COPY --from=builder /app/package.json ./package.json
    
    
    # Expose the port Next.js runs on by default
    EXPOSE 3000
    
    # The CMD to run your Next.js application in production mode
    CMD ["pnpm", "start"]