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
        // Per-step timings. Without this a slow build is just "22 minutes";
        // with it you can see whether the cost is the Rust compile, pip, the
        // apt layer, or plain CPU contention.
        BUILDKIT_PROGRESS = 'plain'
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

        stage('Build Docker Images') {
            steps {
                // Build ONE service. migrator/scraper/web-2/web-3 all resolve
                // to the same shared image tag (see x-app-image in the compose
                // file), so building web-1 satisfies all five. This stage used
                // to run `build` with no target, which rebuilt the same image
                // five times — and deploy.sh then built it a sixth time.
                sh '''
                    time docker-compose -f $COMPOSE_FILE build web-1
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

        stage('Dry-Run — Confirm Deploy') {
            input {
                message "Deploy this build to production?"
                ok "Deploy to Production"
            }
            steps {
                echo 'Deployment approved — proceeding...'
            }
        }

        stage('Deploy to Production') {
            steps {
                sh '''
                    # .env.prod is gitignored so the checkout lacks it, but the
                    # Jenkins container has real secrets at /app/.env.prod
                    # (see docker-compose.jenkins.yml). Stage it into the
                    # workspace: compose 'env_file: .env.prod' resolves here.
                    if [ -f /app/.env.prod ]; then
                        cp /app/.env.prod .env.prod
                        echo '[OK] Staged .env.prod from /app/.env.prod'
                    else
                        echo '[WARN] /app/.env.prod not mounted; deploy may fail'
                    fi
                    chmod +x scripts/deploy.sh
                    # The image is already built by the 'Build Docker Images'
                    # stage; SKIP_BUILD stops deploy.sh rebuilding it.
                    SKIP_BUILD=1 ./scripts/deploy.sh
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
