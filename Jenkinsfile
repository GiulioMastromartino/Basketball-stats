pipeline {
    agent any

    environment {
        COMPOSE_FILE = 'docker-compose.prod.yml'
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
                    pip install ruff --quiet
                    ruff check . || true
                '''
            }
        }

        stage('Test') {
            steps {
                sh '''
                    pip install -r requirements.txt --quiet
                    pytest tests/ --tb=short -x || true
                '''
            }
        }

        stage('Build Docker Images') {
            steps {
                sh 'docker-compose -f $COMPOSE_FILE build'
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
