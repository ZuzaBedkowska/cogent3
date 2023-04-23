pipeline {
  agent any
  stages {
    stage('Build') {
      steps{
        echo 'Building...'
        sh "pwd"
        sh "ls -la"
        sh "docker build -t build_container -f ./Dockerfile_build . > ./logs_build.txt"
        post {
                always{
                    archiveArtifacts(artifacts: 'logs_*.txt', fingerprint: true, followSymlinks: false)
                }
                success {
                    echo 'Success!'
                }
                failure {
                    echo 'Failed in Build!'
                }
            }
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
