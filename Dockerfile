FROM golang:1.24.0-bookworm

# Needed in order to update since apk update configures tzdata.
RUN ln -sf /usr/share/zoneinfo/UTC > /etc/localtime

RUN apt -y update

# Install the Docker client and Git (needed by 'go install')
# Note that you'll need to make sure that /var/run/docker.sock is bind-mounted
# to this container in order for ACT to work.
RUN apt -y install docker git

# Install Act.
RUN go install "github.com/nektos/act@v0.2.74"

# Copy our documentation into the image.
COPY . /app
WORKDIR /app

ENTRYPOINT [ "act", "-P", "ubuntu-24.04=ghcr.io/catthehacker/ubuntu:act-latest" ]
