# Use a minimal image
FROM alpine:3.19

# Create work dir
WORKDIR /app

# Copy your binary and data folders
COPY pocketbase /app/pocketbase
COPY pb_migrations /app/pb_migrations
COPY pb_data_clean /app/pb_data_clean

# Ensure executable permissions
RUN chmod +x /app/pocketbase

EXPOSE 8080

# Run PocketBase on Render's assigned port
CMD ["/app/pocketbase", "serve", "--dir", "./pb_data_clean", "--http", "0.0.0.0:8080"]
