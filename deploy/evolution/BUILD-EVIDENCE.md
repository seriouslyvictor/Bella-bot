# Evolution GO 0.7.2-pr117 build evidence

Recorded on 2026-07-16 from an empty BuildKit cache for `linux/amd64`:

- Image: `bella/evolution-go:0.7.2-pr117-0328955`
- Local manifest-list digest/image ID: `sha256:8873c156a5614c3f104858f16c1133c0d2a035d325fc110c1855bd3d376f8faa`
- Source: `9337afc47e10b86cc896a6f432240e40fee95dd1`
- Source archive SHA-256: `19bda71777291320199fba91deb8620921fc60e2da1ca602bab533f12014b034`
- Patch tip: `03289559d547911d92ad58837db98faeb0c5fd8e`
- Upstream regression test: passed (`go test ./pkg/whatsmeow/service`)
- Entrypoint: `/app/server`
- Embedded version: `0.7.2-pr117-0328955`
- Manager artifact: `/app/manager/dist/index.html` present

Build command:

```console
docker build --no-cache --progress=plain -f deploy/evolution/Dockerfile -t bella/evolution-go:0.7.2-pr117-0328955 .
```

This is local artifact evidence, not a registry manifest digest. If the image is
published, record and deploy the authenticated registry manifest digest for
this exact artifact.
