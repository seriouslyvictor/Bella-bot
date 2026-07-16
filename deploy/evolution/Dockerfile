ARG EVOLUTION_SOURCE_COMMIT=9337afc47e10b86cc896a6f432240e40fee95dd1
ARG EVOLUTION_SOURCE_SHA256=19bda71777291320199fba91deb8620921fc60e2da1ca602bab533f12014b034

FROM golang:1.25.0-alpine@sha256:f18a072054848d87a8077455f0ac8a25886f2397f88bfdd222d6fafbb5bba440 AS build

ARG EVOLUTION_SOURCE_COMMIT
ARG EVOLUTION_SOURCE_SHA256

RUN apk add --no-cache \
      git=2.49.1-r0 \
      build-base=0.5-r3 \
      libjpeg-turbo-dev=3.1.0-r0 \
      libwebp-dev=1.5.0-r0

WORKDIR /build

RUN wget -q -O /tmp/evolution-go.tar.gz \
      "https://codeload.github.com/EvolutionAPI/evolution-go/tar.gz/${EVOLUTION_SOURCE_COMMIT}" \
    && echo "${EVOLUTION_SOURCE_SHA256}  /tmp/evolution-go.tar.gz" | sha256sum -c - \
    && tar -xzf /tmp/evolution-go.tar.gz --strip-components=1 \
    && rm /tmp/evolution-go.tar.gz

COPY deploy/evolution/patches/ /patches/

# Each reviewed PR #117 commit is a repository-owned input. Checks and
# application are deliberately separate so a context mismatch fails the build.
RUN echo "d4c55fde878f585fe4a8cc8ca8081fcd226245ea1c7f281069945c4cee4eb590  /patches/4cc635dd460f70c36ba83285ecbb34589790572f.patch" | sha256sum -c - \
    && git apply --check /patches/4cc635dd460f70c36ba83285ecbb34589790572f.patch \
    && git apply /patches/4cc635dd460f70c36ba83285ecbb34589790572f.patch \
    && echo "26e40ac1485a606c8647b7fbb61e5c918a8f70009aa344d364dce06123b2d232  /patches/f85ea1445373ea142bb12ba0c01dfc85879be212.patch" | sha256sum -c - \
    && git apply --check /patches/f85ea1445373ea142bb12ba0c01dfc85879be212.patch \
    && git apply /patches/f85ea1445373ea142bb12ba0c01dfc85879be212.patch \
    && echo "f6c4fdc65dd00e4ddc98fccff0246460c266ff8b2f3eb56987a6c844c22465c6  /patches/03289559d547911d92ad58837db98faeb0c5fd8e.patch" | sha256sum -c - \
    && git apply --check /patches/03289559d547911d92ad58837db98faeb0c5fd8e.patch \
    && git apply /patches/03289559d547911d92ad58837db98faeb0c5fd8e.patch

# PR #117's test was authored against the repository's former module path. The
# exact 0.7.2 base uses github.com/evolution-foundation/evolution-go, so adapt
# that one test import deterministically, run it, then restore the byte-exact
# upstream test. The runtime tree therefore remains only the three commits.
RUN test "$(grep -Fc '"github.com/EvolutionAPI/evolution-go/pkg/config"' \
      pkg/whatsmeow/service/auth_container_retry_test.go)" -eq 1 \
    && cp pkg/whatsmeow/service/auth_container_retry_test.go /tmp/auth_container_retry_test.go \
    && sed -i 's#github.com/EvolutionAPI/evolution-go/pkg/config#github.com/evolution-foundation/evolution-go/pkg/config#' \
      pkg/whatsmeow/service/auth_container_retry_test.go \
    && test "$(grep -Fc '"github.com/evolution-foundation/evolution-go/pkg/config"' \
      pkg/whatsmeow/service/auth_container_retry_test.go)" -eq 1 \
    && go test ./pkg/whatsmeow/service \
    && mv /tmp/auth_container_retry_test.go pkg/whatsmeow/service/auth_container_retry_test.go

RUN printf '%s\n' '0.7.2-pr117-0328955' > VERSION \
    && CGO_ENABLED=1 go build -trimpath -buildvcs=false \
      -ldflags '-s -w -X main.version=0.7.2-pr117-0328955' \
      -o /out/server ./cmd/evolution-go

FROM alpine:3.19.1@sha256:c5b1261d6d3e43071626931fc004f70149baeba2c8ec672bd4f27761f8e1ad6b AS final

RUN apk add --no-cache \
      tzdata=2025b-r0 \
      ffmpeg=6.1.1-r0 \
      libjpeg-turbo=3.0.1-r0 \
      libwebp=1.3.2-r0 \
      poppler-utils=23.10.0-r0

WORKDIR /app

COPY --from=build /out/server ./server
COPY --from=build /build/manager/dist ./manager/dist
COPY --from=build /build/VERSION ./VERSION

LABEL org.opencontainers.image.title="Bella Evolution GO" \
      org.opencontainers.image.version="0.7.2-pr117" \
      org.opencontainers.image.source="https://github.com/evolution-foundation/evolution-go" \
      org.opencontainers.image.revision="9337afc47e10b86cc896a6f432240e40fee95dd1" \
      io.bella.evolution.patch-commits="4cc635dd460f70c36ba83285ecbb34589790572f,f85ea1445373ea142bb12ba0c01dfc85879be212,03289559d547911d92ad58837db98faeb0c5fd8e" \
      io.bella.evolution.patch-revision="0328955"

ENV TZ=America/Sao_Paulo \
    EVOLUTION_BUILD_IDENTITY=0.7.2-pr117-0328955

ENTRYPOINT ["/app/server"]
