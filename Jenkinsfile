pipeline {
  agent any
  stages {
    stage("Prepare") {
      echo 'Prepare: '
      //usun stare repo
      sh "rm -rf cogent3"
      //usun stare kontenery
      sh "docker prune --all --force"
      //pobierz repo od nowa
    }
    stage("build") {
      steps{
        echo 'Build: '
        sh "ls"
      }
    }
    stage("test") {
      steps{
        echo 'test'
      }
    }
  }
}
