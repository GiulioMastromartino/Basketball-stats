pipeline {
    agent any

    environment {
        COMPOSE_FILE = 'docker-compose.prod.yml'
        APP_DIR = "${WORKSPACE}"
        // docker-compose v1 defaults to the dead "classic" builder, which
        // hangs (futex, no children, no CPU) on the Rust/cargo compile step.
        // Force it to shell out to `docker build` with BuildKit instead.
        DOCKER_BUILDKIT = '1'
        COMPOSE_DOCKER_CLI_BUILD = '1'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: [[name: '*/beta']],
                    extensions: [[$class: 'CloneOption', depth: 1, noTags: true, shallow: true]],
                    userRemoteConfigs: [[url: 'https://github.com/GiulioMastromartino/Basketball-stats.git']]
                ])
            }
        }

        stage('Lint') {
            steps {
                sh '''
                    ruff check . || true
                '''
            }
        }

        stage('Stage Secrets') {
            steps {
                sh '''
                    set -eu
                    # Secrets are gitignored, so a fresh checkout has none.
                    # The Jenkins container receives them as read-only mounts:
                    #   /var/jenkins_home/.env.prod -> /app/.env.prod
                    #   /var/jenkins_home/certs     -> $JENKINS_HOME/certs
                    # Stage them into the workspace before compose runs.
                    if [ ! -f /app/.env.prod ]; then
                        echo '[ERROR] /app/.env.prod is not mounted' >&2
                        exit 1
                    fi
                    cp /app/.env.prod .env.prod
                    chmod 600 .env.prod
                    echo '[OK] Staged .env.prod from /app/.env.prod'

                    CERTS_SRC="${JENKINS_HOME:-/var/jenkins_home}/certs"
                    if [ ! -d "$CERTS_SRC" ]; then
                        echo "[ERROR] TLS cert directory not found: $CERTS_SRC" >&2
                        echo '        See nginx/certs/README.md for the expected files.' >&2
                        exit 1
                    fi
                    mkdir -p nginx/certs
                    cp "$CERTS_SRC"/*.pem nginx/certs/
                    chmod 600 nginx/certs/*privkey*.pem
                    echo "[OK] Staged TLS certs from $CERTS_SRC"
                '''
            }
        }

        stage('Build Docker Images') {
            steps {
                sh 'docker-compose -f $COMPOSE_FILE build'
            }
        }

        stage('Verify Image Has No Secrets') {
            steps {
                sh '''
                    set -eu
                    IMAGE="basketball-stats-web-1:latest"
                    # Defense in depth: the build context must never contain the
                    # env file or TLS private keys (see .dockerignore).
                    if docker run --rm --entrypoint sh "$IMAGE" -c \
                        'test -e /app/.env.prod || test -e /app/nginx/certs/privkey.pem'; then
                        echo "[ERROR] Build context leaked secrets into $IMAGE" >&2
                        exit 1
                    fi
                    echo "[OK] No secret files baked into $IMAGE"
                '''
            }
        }

        stage('Smoke Test') {
            steps {
                sh '''
                    docker-compose -f $COMPOSE_FILE run --rm web-1 python -c "
import sys
print(f'Python {sys.version}')
from core.rust_analytics import safe_percentage
print('Rust module: OK')
print('All dependencies verified')
" || true
                '''
            }
        }

        stage('Deploy to Production') {
            steps {
                sh '''
                    chmod +x scripts/deploy.sh
                    ./scripts/deploy.sh
                '''
            }
        }
    }

    post {
        success {
            echo 'Pipeline completed successfully.'
        }
        failure {
            echo 'Pipeline failed. Check Jenkins logs for details.'
        }
    }
}
