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
#  1. Use /var/data (Render persistent disk mount)
#  2. If /var/data is empty, seed it from pb_data_clean
#  3. Launch PocketBase using /var/data for persistence
# ─────────────────────────────────────────────
CMD ["/bin/sh", "-c", "\
  mkdir -p /var/data && \
  # CRITICAL: Only seed on FIRST deployment (when data.db doesn't exist) \
  # Never overwrite existing production data! \
  if [ ! -f /var/data/data.db ]; then \
    echo '🪴 First deployment detected - seeding initial PocketBase data from pb_data_clean...'; \
    cp -r /app/pb_data_clean/* /var/data/ || true; \
  else \
    echo '💾 Existing PocketBase database found - PRESERVING DATA and skipping seed.'; \
    echo '⚠️  If you see this on a redeploy, your data should be safe.'; \
  fi && \
  echo '🔄 Running migrations...' && \
  /app/pocketbase migrate --dir /var/data --migrationsDir /app/pb_migrations && \
  echo '🚀 Starting PocketBase server...' && \
  /app/pocketbase serve --dir /var/data --http 0.0.0.0:8080 \
"]
