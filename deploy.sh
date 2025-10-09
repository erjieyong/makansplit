#!/bin/bash
set -e

# MakanSplit AWS App Runner Deployment Script
# This script automates deployment to AWS App Runner

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
AWS_REGION="${AWS_REGION:-ap-southeast-1}"
ECR_REPOSITORY="${ECR_REPOSITORY:-makansplit-bot}"
APP_RUNNER_SERVICE="${APP_RUNNER_SERVICE:-makansplit-bot}"

echo -e "${GREEN}🚀 MakanSplit Deployment Script${NC}"
echo "=================================="

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI not found. Please install it first.${NC}"
    exit 1
fi

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not found. Please install it first.${NC}"
    exit 1
fi

# Get AWS Account ID
echo -e "${YELLOW}📋 Getting AWS Account ID...${NC}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
if [ -z "$AWS_ACCOUNT_ID" ]; then
    echo -e "${RED}❌ Failed to get AWS Account ID. Check your AWS credentials.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ AWS Account ID: $AWS_ACCOUNT_ID${NC}"

# ECR URI
ECR_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPOSITORY"

# Step 1: Check if ECR repository exists, create if not
echo -e "\n${YELLOW}📦 Checking ECR repository...${NC}"
if ! aws ecr describe-repositories --repository-names "$ECR_REPOSITORY" --region "$AWS_REGION" &> /dev/null; then
    echo -e "${YELLOW}Creating ECR repository...${NC}"
    aws ecr create-repository \
        --repository-name "$ECR_REPOSITORY" \
        --region "$AWS_REGION" \
        --image-scanning-configuration scanOnPush=true
    echo -e "${GREEN}✓ ECR repository created${NC}"
else
    echo -e "${GREEN}✓ ECR repository exists${NC}"
fi

# Step 2: Login to ECR
echo -e "\n${YELLOW}🔐 Logging in to ECR...${NC}"
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin "$ECR_URI"
echo -e "${GREEN}✓ Logged in to ECR${NC}"

# Step 3: Build Docker image
echo -e "\n${YELLOW}🏗️  Building Docker image...${NC}"
docker build --platform linux/amd64 -t "$ECR_REPOSITORY" .
echo -e "${GREEN}✓ Docker image built${NC}"

# Step 4: Get version from VERSION file
if [ -f "VERSION" ]; then
    APP_VERSION=$(cat VERSION)
else
    echo -e "${RED}❌ VERSION file not found${NC}"
    exit 1
fi

GIT_COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "dev")
VERSION_TAG="v${APP_VERSION}-${GIT_COMMIT}"

echo -e "\n${YELLOW}🏷️  Tagging image...${NC}"
echo -e "Version: ${GREEN}$APP_VERSION${NC}"
echo -e "Commit: ${GREEN}$GIT_COMMIT${NC}"
echo -e "Tag: ${GREEN}$VERSION_TAG${NC}"

docker tag "$ECR_REPOSITORY:latest" "$ECR_URI:latest"
docker tag "$ECR_REPOSITORY:latest" "$ECR_URI:$VERSION_TAG"
docker tag "$ECR_REPOSITORY:latest" "$ECR_URI:v$APP_VERSION"

# Step 5: Push to ECR
echo -e "\n${YELLOW}📤 Pushing to ECR...${NC}"
docker push "$ECR_URI:latest"
docker push "$ECR_URI:$VERSION_TAG"
docker push "$ECR_URI:v$APP_VERSION"
echo -e "${GREEN}✓ Pushed to ECR${NC}"

# Step 6: Check if App Runner service exists
echo -e "\n${YELLOW}🔍 Checking App Runner service...${NC}"
SERVICE_ARN=$(aws apprunner list-services --region "$AWS_REGION" --query "ServiceSummaryList[?ServiceName=='$APP_RUNNER_SERVICE'].ServiceArn" --output text)

if [ -z "$SERVICE_ARN" ]; then
    echo -e "${YELLOW}⚠️  App Runner service not found${NC}"
    echo -e "${YELLOW}Please create the service manually first using AWS Console or CLI${NC}"
    echo -e "${YELLOW}See DEPLOYMENT.md for instructions${NC}"
    exit 1
else
    echo -e "${GREEN}✓ Service found: $SERVICE_ARN${NC}"
fi

# Step 7: Trigger deployment
echo -e "\n${YELLOW}🚀 Triggering App Runner deployment...${NC}"
aws apprunner start-deployment \
    --service-arn "$SERVICE_ARN" \
    --region "$AWS_REGION"

echo -e "${GREEN}✓ Deployment triggered!${NC}"

# Step 8: Get service URL
SERVICE_URL=$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$AWS_REGION" --query "Service.ServiceUrl" --output text)
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "Service: $APP_RUNNER_SERVICE"
echo -e "Version: $VERSION_TAG"
echo -e "Image: $ECR_URI:$VERSION_TAG"
echo -e "URL: https://$SERVICE_URL"
echo -e "\n${YELLOW}💡 Check deployment status:${NC}"
echo -e "aws apprunner describe-service --service-arn $SERVICE_ARN --region $AWS_REGION"
echo -e "\n${YELLOW}💡 View logs:${NC}"
echo -e "aws logs tail /aws/apprunner/$APP_RUNNER_SERVICE --follow"
