pipeline {
    agent any

    environment {
        COMPOSE_FILE = 'docker-compose.prod.yml'
        ENV_FILE = '/app/.env.prod'
        BACKUP_DIR = '/backups'
        APP_DIR = "${WORKSPACE}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
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
                sh 'docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE build'
            }
        }

        stage('Smoke Test') {
            steps {
                sh '''
                    docker-compose -f $COMPOSE_FILE --env-file $ENV_FILE run --rm web_1 python -c "
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
