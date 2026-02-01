# ─────────────────────────────────────────────
#  PocketBase on Render – with persistent data
# ─────────────────────────────────────────────

FROM alpine:3.19

# Set up work directory
WORKDIR /app

# Copy PocketBase binary and migrations
COPY pocketbase /app/pocketbase
COPY pb_migrations /app/pb_migrations
COPY pb_data_clean /app/pb_data_clean

# Give execute permissions to the binary
RUN chmod +x /app/pocketbase

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
  /app/pocketbase serve --dir /data --http 0.0.0.0:8080 \
"]
