FROM rust:1.70

WORKDIR /app

# Install Python
RUN apt-get update && apt-get install -y python3 python3-pip

# Copy Stitch repository
COPY stitch/ /app/stitch/

# Build Stitch
WORKDIR /app/stitch
RUN cargo build --release --bin=compress

# Copy our scripts
WORKDIR /app
COPY *.py /app/
COPY *.sh /app/
COPY battleship_for_stitch.json /app/

# Set up entrypoint
ENTRYPOINT ["/app/run_stitch.sh"]
