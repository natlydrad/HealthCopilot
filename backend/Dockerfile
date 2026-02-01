# ─────────────────────────────────────────────
#  PocketBase on Render – with persistent data
# ─────────────────────────────────────────────

FROM alpine:3.19

# Set up work directory
WORKDIR /app

# Install curl for downloading PocketBase
RUN apk add --no-cache curl

# Download PocketBase Linux binary (amd64 for Render)
# Using the same version as local (v0.36.2)
RUN curl -L https://github.com/pocketbase/pocketbase/releases/download/v0.36.2/pocketbase_0.36.2_linux_amd64.zip -o /tmp/pb.zip && \
    unzip /tmp/pb.zip -d /app && \
    chmod +x /app/pocketbase && \
    rm /tmp/pb.zip

# Copy migrations and seed data
COPY pb_migrations /app/pb_migrations
COPY pb_data_clean /app/pb_data_clean

# Expose the default PocketBase port
EXPOSE 8080

# ─────────────────────────────────────────────
#  Entry point
#  1. Create /data (persistent Render volume)
#  2. If /data is empty, seed it from pb_data_clean
#  3. Launch PocketBase using /data for persistence
# ─────────────────────────────────────────────
CMD ["/bin/sh", "-c", "\
  mkdir -p /data && \
  if [ -z \"$(ls -A /data 2>/dev/null)\" ]; then \
    echo '🪴 Seeding initial PocketBase data from pb_data_clean...'; \
    cp -r /app/pb_data_clean/* /data/ || true; \
  else \
    echo '💾 Existing PocketBase data found, skipping seed.'; \
  fi && \
  echo '🔄 Running migrations...' && \
  /app/pocketbase migrate --dir /data --migrationsDir /app/pb_migrations && \
  echo '🚀 Starting PocketBase server...' && \
  /app/pocketbase serve --dir /data --http 0.0.0.0:8080 \
"]
