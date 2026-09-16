pipeline {
    agent any

    environment {
        COMPOSE_FILE = 'docker-compose.prod.yml'
        APP_DIR = "${WORKSPACE}"
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
                sh 'docker-compose -f $COMPOSE_FILE build'
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
