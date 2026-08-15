#!/usr/bin/env bash
set -e

AUTH=$(cat /var/jenkins_home/cli_token.txt)
JENKINS_URL="http://localhost:8080"

# Fetch CSRF crumb
CRUMB=$(curl -u "${AUTH}" -s "${JENKINS_URL}/crumbIssuer/api/xml?xpath=concat(//crumbRequestField,\":\",//crumb)")

ACTION=${1:-"list-jobs"}

if [ "$ACTION" = "list-jobs" ]; then
    curl -u "${AUTH}" -H "${CRUMB}" -s "${JENKINS_URL}/api/json?tree=jobs[name,url]"
elif [ "$ACTION" = "build" ]; then
    JOB_NAME=${2:-"telco-churn-pipeline"}
    echo "Triggering build for ${JOB_NAME}..."
    curl -u "${AUTH}" -H "${CRUMB}" -X POST -s "${JENKINS_URL}/job/${JOB_NAME}/build"
elif [ "$ACTION" = "last-build-log" ]; then
    JOB_NAME=${2:-"telco-churn-pipeline"}
    curl -u "${AUTH}" -H "${CRUMB}" -s "${JENKINS_URL}/job/${JOB_NAME}/lastBuild/logText/progressiveText?start=0"
elif [ "$ACTION" = "last-build-status" ]; then
    JOB_NAME=${2:-"telco-churn-pipeline"}
    curl -u "${AUTH}" -H "${CRUMB}" -s "${JENKINS_URL}/job/${JOB_NAME}/lastBuild/api/json?tree=number,result,building,duration"
fi
