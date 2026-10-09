# Microservice build contexts

The major microservice Dockerfiles use the repository root as their build context
because they copy both service files and shared files from `common/`.
Each has a `Dockerfile.dockerignore` beside it that excludes everything except
its local `COPY` and `ADD` inputs. The AI agent and docs dispatcher also have
`Dockerfile.dev.dockerignore` for their development Dockerfiles.

Use modern Docker with BuildKit enabled. Dockerfile-specific ignore files take
precedence over the root `.dockerignore`; their patterns are relative to the
build context root, not the directory containing the ignore file. Compose
continues to use the existing contexts and Dockerfile paths.

When adding or changing a local `COPY` or `ADD`, update the corresponding
allowlist. Include ancestor directories and `/**` when copying an entire
directory. `COPY --from` uses another build stage and needs no local allowlist
entry. Keep exclusions for local environment files and caches after the
allowlist entries so those exclusions still apply inside included directories.

The cyclomatic complexity and RRD images allow `services/` for the default
`SCRIPT_GEN_LOC` build argument. If you override that argument, explicitly
allow the new directory and its shell scripts in the corresponding ignore file.

For example, from the repository root:

```sh
docker compose -f ai_agents_framework/ai_agent/compose-default.prod.yaml \
  --progress plain build ai_agent
```

The build output reports the transferred context size. These allowlists exclude
unrelated services, repository metadata, tests, and documentation from the
major service builds. Shared infrastructure images and separate test Dockerfiles
continue to use the root ignore policy.
