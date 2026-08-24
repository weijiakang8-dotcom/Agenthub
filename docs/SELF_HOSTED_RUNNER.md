# Production self-hosted runner

AgentHub production deploys run on a repository-scoped GitHub Actions runner. CI remains on GitHub-hosted runners. Production deployment is manual through `workflow_dispatch` and requires approval in the `production` Environment.

## Runtime layout

- User: `agenthub-runner`
- Runner: `/opt/actions-runner-agenthub`
- Work directory: `/var/lib/agenthub-runner/_work`
- Label: `agenthub-production`
- Production checkout: `/home/ubuntu/agenthub`
- Root-managed wrapper: `/usr/local/sbin/deploy-agenthub`
- Deployment lock: `/run/lock/agenthub-production.lock`

The runner user is not in the `docker` or `sudo` group. It can only run the root-owned deployment wrapper with a SHA argument through `/etc/sudoers.d/agenthub-runner-deploy`. Docker group membership is intentionally avoided because it is effectively root access.

The workflow does not checkout repository code on the production runner. The wrapper validates a full commit SHA against `origin/main`, locks deployment concurrency, backs up PostgreSQL, refuses schema changes, builds and recreates application containers, validates `BUILD_SHA`, validates local and public health, and rolls back to the pre-deployment SHA on failure.

## Deploy

1. Confirm the target is a full 40-character SHA on `main` and its required CI checks passed.
2. Open **Actions > Deploy AgentHub > Run workflow** on `main`.
3. Enter the full SHA.
4. Approve the pending `production` Environment deployment.
5. Confirm the job and public `/health.build_sha` match the target SHA.

## Pause

Disable the workflow in GitHub Actions or stop the runner:

```bash
sudo systemctl stop actions.runner.weijiakang8-dotcom-Agenthub.agenthub-prod-193-112-130-181.service
```

Production containers continue running when the runner is stopped.

## Resume

```bash
sudo systemctl start actions.runner.weijiakang8-dotcom-Agenthub.agenthub-prod-193-112-130-181.service
```

## Roll back

The controlled wrapper automatically attempts rollback after activation failures. For an operator-directed rollback, run the wrapper with a previously tested full SHA that remains in `main` and has successful required CI checks:

```bash
sudo /usr/local/sbin/deploy-agenthub <full-main-sha>
```

Do not perform an application rollback across an incompatible database migration without a separate database recovery plan.

## Uninstall

1. Disable the deployment workflow.
2. Stop and uninstall the service with the official runner `svc.sh`.
3. Remove the repository runner in GitHub Settings.
4. Remove the exact sudoers rule and root-owned wrapper.
5. Remove the runner installation and work directories only after preserving required diagnostics.

Removing the runner does not stop or remove production containers. Manual deployment remains available to authorized server operators.
