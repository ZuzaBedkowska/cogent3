pipeline {
  agent any
  stages {
    stage('Build') {
      steps{
        echo 'Building...'
        sh "pwd"
        sh "ls -la"
        sh "docker build -t build_container -f ./Dockerfile_build . > ./logs_build.txt"
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
