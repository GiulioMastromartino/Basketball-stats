# TLS certificates

Certificate files are **not tracked by git** and are excluded from the Docker
build context (see `.gitignore` and `.dockerignore`). Private keys must never
be committed or baked into an image.

The Compose stack expects these files in `nginx/certs/`:

| File | Used for |
|------|----------|
| `fullchain.pem` | `www.superhooper.work.gd` certificate chain |
| `privkey.pem` | `www.superhooper.work.gd` private key |
| `hoopslab-fullchain.pem` | `hoopslab.2bd.net` certificate chain |
| `hoopslab-privkey.pem` | `hoopslab.2bd.net` private key |

## Jenkins

Place the four files under `/var/jenkins_home/certs` on the Docker host:

```bash
install -d -m 700 /var/jenkins_home/certs
install -m 600 privkey.pem hoopslab-privkey.pem /var/jenkins_home/certs/
install -m 644 fullchain.pem hoopslab-fullchain.pem /var/jenkins_home/certs/
```

The pipeline's **Stage Secrets** step copies them into `nginx/certs/` before
building and deploying.

## Local runs

Copy the same files into this directory manually. They will be ignored by git
and excluded from the image.

## Rotation

If a private key was ever committed, pushed, or baked into an image, treat it
as compromised and reissue the certificate. Removing the file from the current
commit does not remove it from git history.
