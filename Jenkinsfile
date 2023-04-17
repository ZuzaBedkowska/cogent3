pipeline {
  agent any
  environment {
        MAJOR_VERSION = "1"
        MINOR_VERSION = "1"
        BUILD_VERSION = sh(returnStdout: true, script: 'echo ${BUILD_NUMBER}').trim()
        VERSION = "${MAJOR_VERSION}.${MINOR_VERSION}.${BUILD_VERSION}"
        DOCKERHUB_CREDENTIALS = credentials('dockerhub')
    }
  stages {
    stage('Build') {
      steps{
        echo 'Building...'
        sh "ls -la"
        sh "DOCKER_TLS_VERIFY=0 docker build -t build_container -f Dockerfile_build > logs_build.txt"
      }
    }
    stage('Test') {
      steps{
        echo 'Testing...'
      }
    }
    stage ('Deploy') {
      steps{
       echo 'Deploying...'
      }
    }
  }
}
