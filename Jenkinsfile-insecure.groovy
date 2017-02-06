stage('Prepare devkit and test containers') {
    sh 'make update-devkit'
}

try {
    stage('make flake8') {
        sh 'make flake8'
    }

    stage('make test') {
        sh 'make test'
    }

} finally {
    stage('Cleanup docker containers'){
        sh 'make clean-containers'
        sh "docker rmi -f adminrouter-devkit || true"
    }
}
