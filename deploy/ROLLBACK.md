# Rollback (Fly.io)

The volume survives a rollback; only the image changes. There are no database
migrations to undo.

1. List releases and note the tag before the bad one:

   ```sh
   fly releases
   ```

2. Redeploy that image:

   ```sh
   fly deploy --image registry.fly.io/process-watcher:<previous-tag>
   ```

3. Verify:

   ```sh
   fly status
   curl -fsS https://process-watcher.fly.dev/healthz
   ```

4. If the Machine itself is unhealthy, `fly machine list` and restart it; the volume is
   reattached on boot. Do not delete the volume to "fix" a bad release — it holds
   `runs/` and the response cache.

Rehearse this once before submission (G7 extra). Record the release tag and the time in
`docs/PROGRESS.md`.
