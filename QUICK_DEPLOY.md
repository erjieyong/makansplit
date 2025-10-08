# Quick Deployment Guide

This guide shows you how to deploy MakanSplit to AWS App Runner using the automated deployment script.

## Prerequisites

1. **AWS CLI** installed and configured
   ```bash
   aws configure
   ```

2. **Docker** installed and running

3. **Git** repository initialized with commits

## One-Time Setup

### Step 1: Create App Runner Service (First Time Only)

You need to create the App Runner service once. Run this command:

```bash
aws apprunner create-service \
  --service-name makansplit-bot \
  --source-configuration '{
    "ImageRepository": {
      "ImageIdentifier": "YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "8080",
        "RuntimeEnvironmentVariables": {
          "TELEGRAM_BOT_TOKEN": "YOUR_BOT_TOKEN",
          "OPENROUTER_API_KEY": "YOUR_API_KEY",
          "OPENROUTER_MODEL": "google/gemini-2.5-flash-lite-preview-09-2025"
        }
      }
    },
    "AutoDeploymentsEnabled": false,
    "AuthenticationConfiguration": {
      "AccessRoleArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/AppRunnerECRAccessRole"
    }
  }' \
  --instance-configuration '{
    "Cpu": "1 vCPU",
    "Memory": "2 GB"
  }' \
  --region ap-southeast-1
```

**OR** create via AWS Console:
1. Go to [AWS App Runner Console](https://console.aws.amazon.com/apprunner)
2. Click **Create service**
3. Follow the instructions in DEPLOYMENT.md

### Step 2: Create IAM Role for ECR Access (if needed)

If you don't have the `AppRunnerECRAccessRole`, create it:

```bash
# Create trust policy
cat > trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "build.apprunner.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name AppRunnerECRAccessRole \
  --assume-role-policy-document file://trust-policy.json

# Attach policy
aws iam attach-role-policy \
  --role-name AppRunnerECRAccessRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
```

## Deploy

Once setup is complete, deploying is simple:

### Option 1: Quick Deploy (Recommended)

```bash
./deploy.sh
```

That's it! The script will:
- ✅ Create ECR repository if needed
- ✅ Build Docker image
- ✅ Tag with version (timestamp + git commit)
- ✅ Push to ECR
- ✅ Trigger App Runner deployment
- ✅ Show service URL

### Option 2: Custom Configuration

Set environment variables before deploying:

```bash
export AWS_REGION="ap-southeast-1"
export ECR_REPOSITORY="my-custom-name"
export APP_RUNNER_SERVICE="my-service-name"
./deploy.sh
```

## Monitor Deployment

### Check Deployment Status

```bash
aws apprunner list-operations \
  --service-arn $(aws apprunner list-services --region ap-southeast-1 --query "ServiceSummaryList[?ServiceName=='makansplit-bot'].ServiceArn" --output text) \
  --region ap-southeast-1
```

### View Logs

```bash
aws logs tail /aws/apprunner/makansplit-bot --follow
```

### Get Service URL

```bash
aws apprunner describe-service \
  --service-arn $(aws apprunner list-services --region ap-southeast-1 --query "ServiceSummaryList[?ServiceName=='makansplit-bot'].ServiceArn" --output text) \
  --region ap-southeast-1 \
  --query "Service.ServiceUrl" \
  --output text
```

## Troubleshooting

### "ECR repository not found"
The script will create it automatically on first run.

### "App Runner service not found"
You need to create the service first (see Step 1 above).

### "Docker build failed"
Make sure Docker is running and you have enough disk space.

### "AWS credentials not found"
Run `aws configure` to set up your credentials.

## Update Environment Variables

To update environment variables after deployment:

```bash
# Get service ARN
SERVICE_ARN=$(aws apprunner list-services --region ap-southeast-1 --query "ServiceSummaryList[?ServiceName=='makansplit-bot'].ServiceArn" --output text)

# Update service with new environment variables
aws apprunner update-service \
  --service-arn $SERVICE_ARN \
  --source-configuration '{
    "ImageRepository": {
      "ImageConfiguration": {
        "RuntimeEnvironmentVariables": {
          "TELEGRAM_BOT_TOKEN": "NEW_TOKEN",
          "OPENROUTER_API_KEY": "NEW_KEY"
        }
      }
    }
  }' \
  --region ap-southeast-1
```

## Rollback

To rollback to a previous version:

```bash
# List image tags
aws ecr list-images \
  --repository-name makansplit-bot \
  --region ap-southeast-1

# Deploy specific version
docker pull YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:VERSION_TAG
docker tag YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:VERSION_TAG YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest

# Trigger deployment
./deploy.sh
```

## Cost Estimation

- **App Runner**: ~$62/month (1 vCPU, 2 GB, 24/7)
- **ECR Storage**: ~$0.10/GB/month
- **Data Transfer**: Usually negligible for a bot

See DEPLOYMENT.md for detailed cost breakdown.

## Quick Commands Reference

```bash
# Deploy
./deploy.sh

# View logs
aws logs tail /aws/apprunner/makansplit-bot --follow

# Check service status
aws apprunner describe-service --service-arn $(aws apprunner list-services --region ap-southeast-1 --query "ServiceSummaryList[?ServiceName=='makansplit-bot'].ServiceArn" --output text) --region ap-southeast-1

# Stop service (to save costs)
aws apprunner pause-service --service-arn $SERVICE_ARN --region ap-southeast-1

# Resume service
aws apprunner resume-service --service-arn $SERVICE_ARN --region ap-southeast-1

# Delete service
aws apprunner delete-service --service-arn $SERVICE_ARN --region ap-southeast-1
```
